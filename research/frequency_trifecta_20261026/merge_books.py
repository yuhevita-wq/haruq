import argparse,collections,decimal,gzip,hashlib,json
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();OUT=args.output
public={}
with gzip.open(OUT/'matched_final_trifecta_books.jsonl.gz','rt') as f:
 for line in f:
  r=json.loads(line);assert r['race_id'] not in public;public[r['race_id']]=r
counts=collections.Counter();conflicts=[];totalquotes=0;seen=set()
def same(a,b):return a.keys()==b.keys() and all(decimal.Decimal(a[k])==decimal.Decimal(b[k]) for k in a)
target=OUT/'final_trifecta_books_2025H2_2026H1.jsonl.gz'
with gzip.open(target,'wt',encoding='utf-8') as out:
 with gzip.open(OUT/'cipher_validated_trifecta_books.jsonl.gz','rt') as f:
  for line in f:
   r=json.loads(line);rid=r['race_id'];assert rid not in seen;seen.add(rid)
   other=public.pop(rid,None)
   if other is not None:
    if not same(r['odds'],other['odds']):
     conflicts.append(dict(race_id=rid,differing_prices=sum(decimal.Decimal(v)!=decimal.Decimal(other['odds'].get(k,'NaN')) for k,v in r['odds'].items())));continue
    counts['both_agree']+=1;sources=['public_odds_only','cipher_archive']
   else:counts['cipher_only']+=1;sources=['cipher_archive']
   r['sources']=sources;out.write(json.dumps(r,separators=(',',':'))+'\n');totalquotes+=len(r['odds'])
 for rid,r in sorted(public.items()):
  counts['public_only']+=1;r['sources']=['public_odds_only'];out.write(json.dumps(r,separators=(',',':'))+'\n');totalquotes+=len(r['odds'])
audit=dict(admitted_races=sum(counts.values()),admitted_quotes=totalquotes,source_counts=dict(counts),cross_source_conflicting_races=len(conflicts),cross_source_conflicts=conflicts,quarantine_rule='Different candidate prices across otherwise independently valid complete books quarantine the entire race; never choose the most profitable source.',output_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),output_bytes=target.stat().st_size)
(OUT/'merge_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
print('MERGED',json.dumps({k:v for k,v in audit.items() if k!='cross_source_conflicts'}),flush=True)
