import argparse,collections,csv,decimal,datetime,gzip,hashlib,itertools,json
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--workdir',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--records',type=Path,required=True);args=parser.parse_args()
P=args.workdir;OUT=args.output;OUT.mkdir(parents=True,exist_ok=True)
records={r['race_id']:r for r in csv.DictReader(args.records.open()) if '2025-07-01'<=r['date']<'2026-07-01'}
seen={};counts=collections.Counter();bad=[];matched=[];dupes=[]
def netid(rid):
    assert len(rid)==16 and rid.isdecimal()
    day=datetime.datetime.strptime(rid[2:10],'%Y%m%d').date()+datetime.timedelta(days=int(rid[10:12])-1)
    return day.strftime('%Y%m%d')+rid[:2]+f'{int(rid[12:16]):02d}'
target=OUT/'matched_final_trifecta_books.jsonl.gz'
with gzip.open(target,'wt',encoding='utf-8') as out:
 for year in [2025,2026]:
  with gzip.open(P/f'odds_{year}.jsonl.gz','rt',encoding='utf-8') as f:
   for line in f:
    obj=json.loads(line,parse_float=decimal.Decimal);counts['source_rows']+=1
    rid=netid(obj['race_id']);r=records.get(rid)
    if r is None:continue
    counts['overlapping_rows']+=1
    q=obj['odds'].get('3連単',{});bikes=list(map(int,r['ranked_bikes'].split('>')))
    exp={'-'.join(map(str,t)) for t in itertools.permutations(bikes,3)}
    if set(q)!=exp:
     counts['incomplete']+=1;bad.append(dict(race_id=rid,source_id=obj['race_id'],reason='incomplete_candidate_set',observed=len(q),expected=len(exp)));continue
    try:
     norm={s:decimal.Decimal(str(v)) for s,v in q.items()}
     assert all(v.is_finite() and v>=1 for v in norm.values())
    except (AssertionError,decimal.InvalidOperation):
     counts['invalid']+=1;bad.append(dict(race_id=rid,reason='invalid_price'));continue
    normalized={s:str(v) for s,v in norm.items()}
    h=hashlib.sha256(json.dumps(normalized,sort_keys=True).encode()).hexdigest()
    if rid in seen:
     counts['duplicate_same' if seen[rid]==h else 'duplicate_conflict']+=1
     dupes.append(dict(race_id=rid,conflict=seen[rid]!=h));continue
    seen[rid]=h
    winning='-'.join(r['actual_bikes'].split('>')[:3])
    if norm[winning]*100!=decimal.Decimal(r['trifecta_payout_yen_per_100']):
     counts['payout_mismatch']+=1;bad.append(dict(race_id=rid,source_id=obj['race_id'],reason='payout_mismatch',winning=winning,odds=str(norm[winning]),payout=r['trifecta_payout_yen_per_100']));continue
    counts['matched']+=1;counts['ticket_quotes']+=len(q);matched.append(rid)
    out.write(json.dumps(dict(race_id=rid,source_race_id=obj['race_id'],odds=normalized),ensure_ascii=False,separators=(',',':'))+'\n')
summary=dict(source='data/odds_only/odds_2025.jsonl.gz and odds_2026.jsonl.gz',source_export='research/odds_universe_v1/build_odds_only.py',direct_combination_order=True,eligible_races=len(records),counts=dict(counts),issues=bad,duplicates=dupes,matched_races=len(matched),missing_or_rejected_races=len(records)-len(matched),output_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),output_bytes=target.stat().st_size)
(OUT/'source_audit.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k not in ['issues','duplicates']},ensure_ascii=False),flush=True)
print('ISSUE_EXAMPLES',json.dumps(bad[:10],ensure_ascii=False),flush=True)
assert counts['duplicate_conflict']==0
