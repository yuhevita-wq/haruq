import argparse,collections,csv,decimal,gzip,hashlib,json,math
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--records',type=Path,required=True);args=parser.parse_args()
P=args.output
records={r['race_id']:r for r in csv.DictReader(args.records.open())}
plan=json.load(open(P/'estimation_plan.json'))
assert all(r['model_sha256']==plan['model_sha256'] for r in records.values())
summary=json.load(open(P/'summary.json'));merge=json.load(open(P/'merge_audit.json'))
cells=list(csv.DictReader(open(P/'trifecta_price_conditional_frequencies.csv')))
pattern_den=collections.Counter();group_hits=collections.Counter();group_den=collections.Counter();example_counts=collections.Counter();seen=set();group_n=collections.Counter();quote_count=0
for c in cells:
 n=int(c['opportunities']);k=int(c['hits']);p=float(c['frequency']);lo=float(c['wilson95_lower']);hi=float(c['wilson95_upper'])
 assert 0<=k<=n and n>0 and abs(p-k/n)<1e-15 and 0<=lo<=p+1e-14 and p<=hi+1e-14 and hi<=1
 if k==0:assert hi>0
 group=tuple(c[x] for x in ['period','band_scheme','band','rider_count'])
 pattern_den[group+(c['rank_pattern'],)]+=n;group_hits[group]+=k;group_den[group]+=n
 if c['band_scheme']=='exacta_band' and c['period']=='all_20250701_20260630' and c['rider_count']=='7' and c['rank_pattern'] in ['4>2>1','1>2>3']:
  example_counts[(c['band'],c['rank_pattern'],c['odds_bin'],'n')]=n;example_counts[(c['band'],c['rank_pattern'],c['odds_bin'],'k')]=k
independent=collections.Counter();exact_checks=0
bounds=[decimal.Decimal(str(v)) for v in [4,10,20,50,100,200,500,1000]]
labels=['(0,4]','(4,10]','(10,20]','(20,50]','(50,100]','(100,200]','(200,500]','(500,1000]','(1000,infinity)']
with gzip.open(P/'final_trifecta_books_2025H2_2026H1.jsonl.gz','rt') as f:
 for line in f:
  book=json.loads(line);rid=book['race_id'];assert rid not in seen;seen.add(rid);r=records[rid]
  n=int(r['rider_count']);bikes=list(map(int,r['ranked_bikes'].split('>')));quote_count+=len(book['odds'])
  assert len(book['odds'])==n*(n-1)*(n-2)
  winning='-'.join(r['actual_bikes'].split('>')[:3]);assert decimal.Decimal(book['odds'][winning])*100==decimal.Decimal(r['trifecta_payout_yen_per_100']);exact_checks+=1
  for scheme in ['exacta_band','trifecta_band']:
   for ph in ['all_20250701_20260630','2025H2' if r['date']<'2026-01-01' else '2026H1']:
    group_n[(ph,scheme,r[scheme],str(n))]+=1
  if n!=7:continue
  for pat in ['4>2>1','1>2>3']:
   key='-'.join(str(bikes[int(i)-1]) for i in pat.split('>'));value=decimal.Decimal(book['odds'][key])
   bucket=next((i for i,b in enumerate(bounds) if value<=b),8);label=labels[bucket]
   independent[(r['exacta_band'],pat,label,'n')]+=1;independent[(r['exacta_band'],pat,label,'k')]+=int(key==winning)
assert independent==example_counts
for group,count in group_n.items():
 n=int(group[3]);assert group_hits[group]==count and group_den[group]==count*n*(n-1)*(n-2)
for key,count in pattern_den.items():assert count==group_n[key[:-1]]
assert len(seen)==summary['matched_races']==merge['admitted_races']
assert quote_count==summary['ticket_quote_opportunities']==merge['admitted_quotes']
for name,h in summary['output_sha256'].items():assert hashlib.sha256((P/name).read_bytes()).hexdigest()==h
assert hashlib.sha256((P/'final_trifecta_books_2025H2_2026H1.jsonl.gz').read_bytes()).hexdigest()==summary['books_input_sha256']
result=dict(status='passed',matched_races=len(seen),candidate_quotes=quote_count,exact_payout_checks=exact_checks,
            exported_cells=len(cells),exported_group_checks=len(group_n),pattern_denominator_partition_checks=len(pattern_den),
            independently_recounted_examples='Every band and price bin for 7-rider patterns4>2>1 and1>2>3, using Decimal values and actual bike combinations.',
            comparison='Independent scalar Decimal binning versus vectorized NumPy estimates; all matched.',production_changed=False)
(P/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result),flush=True)
