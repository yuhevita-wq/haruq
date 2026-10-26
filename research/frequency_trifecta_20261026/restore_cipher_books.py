import argparse,collections,concurrent.futures,csv,datetime,decimal,functools,gzip,hashlib,io,itertools,json,subprocess,urllib.request
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--workdir',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--records',type=Path,required=True);args=parser.parse_args()
ROOT=args.workdir;CACHE=ROOT/'cipher_cache';CACHE.mkdir(exist_ok=True)
OUT=args.output;OUT.mkdir(parents=True,exist_ok=True)
manifest=json.load(open(ROOT/'cipher_manifest.json'))
records={r['race_id']:r for r in csv.DictReader(args.records.open()) if '2025-07-01'<=r['date']<'2026-07-01'}
def retrieve(item):
 p=CACHE/(item['sha']+'.p7m')
 if p.exists():data=p.read_bytes()
 else:
  url='https://raw.githubusercontent.com/'+manifest['source_repo']+'/'+manifest['source_commit']+'/'+item['path']
  data=urllib.request.urlopen(url,timeout=90).read();p.write_bytes(data)
 assert len(data)==item['size']
 assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==item['sha']
 return p
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
 paths=list(pool.map(retrieve,manifest['files']))
print('ARCHIVES_VERIFIED',len(paths),sum(p.stat().st_size for p in paths),flush=True)
@functools.lru_cache(maxsize=None)
def netid(rid):
 day=datetime.datetime.strptime(rid[2:10],'%Y%m%d').date()+datetime.timedelta(days=int(rid[10:12])-1)
 return day.strftime('%Y%m%d')+rid[:2]+f'{int(rid[12:16]):02d}'
books={};conflicts=set();counts=collections.Counter();meta={}
for ix,(item,path) in enumerate(zip(manifest['files'],paths)):
 compressed=subprocess.check_output(['openssl','cms','-decrypt','-binary','-inform','DER','-in',str(path),'-recip',str(ROOT/'keys/cert.pem'),'-inkey',str(ROOT/'keys/private.pem')],stderr=subprocess.PIPE)
 with gzip.open(io.BytesIO(compressed),'rt',encoding='utf-8-sig',newline='') as f:
  for row in csv.DictReader(f):
   if row['bet_type']!='3rentan':continue
   counts['source_trifecta_quote_rows']+=1
   original=row['race_id'];rid=netid(original)
   if rid not in records:continue
   counts['overlap_quote_rows']+=1
   val=decimal.Decimal(row['odds_min'])
   if not val.is_finite() or val<1 or val!=decimal.Decimal(row['odds_max']):
    conflicts.add(rid);counts['invalid_values']+=1;continue
   # Legacy first_place_block treats a left row label as second place.
   # Historical source tables label THIRD place on rows and SECOND on columns.
   # Uniform semantic normalization a-b-c -> a-c-b; never choose by race outcome.
   a,b,c=row['selection'].split('-');selection='-'.join([a,c,b])
   q=books.setdefault(rid,{})
   if selection in q:
    if q[selection]!=val:conflicts.add(rid);counts['conflicting_duplicate_quotes']+=1
    else:counts['identical_duplicate_quotes']+=1
   q[selection]=val
   m=meta.setdefault(rid,dict(source_race_id=original,times=set(),paths=set()))
   m['times'].add(row['odds_time_jst']);m['paths'].add(item['path'])
 if ix%40==0:print('CIPHER_PARSED',ix,len(paths),'books',len(books),flush=True)
bad=[];admitted=0;quotes=0
with gzip.open(OUT/'cipher_validated_trifecta_books.jsonl.gz','wt',encoding='utf-8') as f:
 for rid,q in sorted(books.items()):
  r=records[rid];bikes=list(map(int,r['ranked_bikes'].split('>')))
  expected={'-'.join(map(str,t)) for t in itertools.permutations(bikes,3)}
  reason=''
  if rid in conflicts:reason='conflicting_or_invalid_quotes'
  elif set(q)!=expected:reason='incomplete_candidate_set'
  else:
   winning='-'.join(r['actual_bikes'].split('>')[:3])
   if q[winning]*100!=decimal.Decimal(r['trifecta_payout_yen_per_100']):reason='winning_payout_mismatch'
  if reason:
   issue=dict(race_id=rid,reason=reason)
   if reason=='winning_payout_mismatch':issue.update(winning=winning,odds=str(q[winning]),payout=r['trifecta_payout_yen_per_100'])
   bad.append(issue);continue
  m=meta[rid]
  f.write(json.dumps(dict(race_id=rid,source_race_id=m['source_race_id'],times=sorted(m['times']),source_paths=sorted(m['paths']),odds={k:str(v) for k,v in q.items()}),separators=(',',':'))+'\n')
  admitted+=1;quotes+=len(q)
summary=dict(source_commit=manifest['source_commit'],source_archives=len(paths),normalization='Uniform legacy selection a-b-c -> a-c-b: source table rows are third place, columns second place.',counts=dict(counts),overlapping_race_books=len(books),admitted_races=admitted,admitted_quotes=quotes,quarantined=len(bad),quarantine_reasons=dict(collections.Counter(x['reason'] for x in bad)),issues=bad)
(OUT/'cipher_source_audit.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print('CIPHER_AUDIT',json.dumps({k:v for k,v in summary.items() if k!='issues'}),flush=True)
print('ISSUES',json.dumps(bad[:10]),flush=True)
