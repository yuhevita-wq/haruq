import argparse,collections,csv,gzip,hashlib,itertools,json,math
from pathlib import Path
import numpy as np
parser=argparse.ArgumentParser();parser.add_argument('--records',type=Path,required=True);parser.add_argument('--books',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
OUT=args.output;plan=json.load(open(OUT/'estimation_plan.json'))
records={r['race_id']:r for r in csv.DictReader(args.records.open()) if '2025-07-01'<=r['date']<'2026-07-01'}
assert len(records)==21912 and all(r['model']==plan['model'] for r in records.values())
limits=np.array(plan['odds_upper_boundaries'],dtype=float);labels=plan['odds_bins']
perms={n:list(itertools.permutations(range(1,n+1),3)) for n in range(5,10)}
patternidx={n:{p:i for i,p in enumerate(ps)} for n,ps in perms.items()}
den={};hits={};group_races=collections.Counter();matched=set();coverage=collections.Counter();quote_total=0
def phase(day):return '2025H2' if day<'2026-01-01' else '2026H1'
for r in records.values():
 for scheme in ['exacta_band','trifecta_band']:
  coverage[(phase(r['date']),scheme,r[scheme],int(r['rider_count']),'eligible')]+=1
with gzip.open(args.books,'rt') as f:
 for ix,line in enumerate(f):
  book=json.loads(line);rid=book['race_id'];assert rid not in matched;matched.add(rid);r=records[rid]
  n=int(r['rider_count']);bikes=list(map(int,r['ranked_bikes'].split('>')));ps=perms[n]
  keys=['-'.join(str(bikes[k-1]) for k in p) for p in ps]
  assert set(keys)==set(book['odds'])
  quotes=np.array([float(book['odds'][key]) for key in keys]);assert np.isfinite(quotes).all() and (quotes>=1).all()
  buckets=np.searchsorted(limits,quotes,side='left')
  actual=tuple(map(int,r['trifecta_rank_pattern'].split('>')));winner=patternidx[n][actual]
  # Quote strings were verified exactly to payout before this float-only binning step.
  assert abs(quotes[winner]*100-float(r['trifecta_payout_yen_per_100']))<1e-5
  inds=np.arange(len(ps));quote_total+=len(ps)
  for scheme in ['exacta_band','trifecta_band']:
   key=(phase(r['date']),scheme,r[scheme],n)
   if key not in den:den[key]=np.zeros((len(ps),len(labels)),dtype=np.int64);hits[key]=np.zeros_like(den[key])
   den[key][inds,buckets]+=1;hits[key][winner,buckets[winner]]+=1;group_races[key]+=1
   coverage[key+('matched',)]+=1
  if ix%3000==0:print('QUOTED_RACES_PROCESSED',ix,flush=True)
for key in list(den):
 combined=('all_20250701_20260630',)+key[1:]
 if combined not in den:den[combined]=np.zeros_like(den[key]);hits[combined]=np.zeros_like(hits[key])
 den[combined]+=den[key];hits[combined]+=hits[key];group_races[combined]+=group_races[key]

def wilson(k,n):
 z=1.959963984540054;p=k/n;d=1+z*z/n;c=(p+z*z/(2*n))/d;h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
 return (0. if k==0 else max(0.,c-h)),(1. if k==n else min(1.,c+h))
fieldnames=['period','band_scheme','band','rider_count','market','rank_pattern','odds_bin','hits','opportunities','frequency','wilson95_lower','wilson95_upper']
cells=zero=0
with (OUT/'trifecta_price_conditional_frequencies.csv').open('w',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fieldnames);w.writeheader()
 for key in sorted(den):
  ph,scheme,band,n=key
  assert int(hits[key].sum())==group_races[key]
  assert np.all(den[key].sum(axis=1)==group_races[key])
  assert int(den[key].sum())==group_races[key]*len(perms[n])
  for i,bucket in zip(*np.nonzero(den[key])):
   count=int(hits[key][i,bucket]);opps=int(den[key][i,bucket]);lo,hi=wilson(count,opps)
   w.writerow(dict(period=ph,band_scheme=scheme,band=band,rider_count=n,market='trifecta',rank_pattern='>'.join(map(str,perms[n][i])),odds_bin=labels[bucket],hits=count,opportunities=opps,frequency=count/opps,wilson95_lower=lo,wilson95_upper=hi))
   cells+=1;zero+=count==0
cov=[]
for ph,scheme,band,n in sorted({k[:4] for k in coverage}):
 eligible=coverage[(ph,scheme,band,n,'eligible')];got=coverage[(ph,scheme,band,n,'matched')]
 cov.append(dict(period=ph,band_scheme=scheme,band=band,rider_count=n,eligible_races=eligible,matched_races=got,unavailable_or_quarantined_races=eligible-got))
with (OUT/'trifecta_price_coverage.csv').open('w',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(cov[0]));w.writeheader();w.writerows(cov)
summary=dict(model=plan['model'],eligible_races=len(records),matched_races=len(matched),unavailable_or_quarantined_races=len(records)-len(matched),ticket_quote_opportunities=quote_total,
             estimated_cells=cells,zero_hit_cells=zero,matched_periods=dict(collections.Counter(phase(records[rid]['date']) for rid in matched)),
             grouping='Primary exacta_band for cross-market HIGH/MED comparison; separate native trifecta_band. Never merge schemes.',
             record_input_sha256=hashlib.sha256(args.records.read_bytes()).hexdigest(),books_input_sha256=hashlib.sha256(args.books.read_bytes()).hexdigest(),
             production_changed=False,selection_performed=False,purchase_or_le4_filter_applied=False,
             limitations=['Final odds, not pre-purchase snapshots.','Previously viewed archive, not a newly untouched holdout.','Broad conditional historical frequencies, not calibrated individual-race probabilities.','Wilson interval assumes approximate independent binomial trials; no clustering/drift/multiple-search adjustment.'])
summary['output_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('*.csv')}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print('ESTIMATION_COMPLETE',json.dumps(summary,ensure_ascii=False),flush=True)
for scheme,band in [('exacta_band','HIGH'),('exacta_band','MED+'),('exacta_band','MED')]:
 key=('all_20250701_20260630',scheme,band,7)
 for pat in [(4,2,1),(1,2,3)]:
  for b in [3,4,5,6,7,8]:
   i=patternidx[7][pat];opps=int(den[key][i,b]);count=int(hits[key][i,b])
   if opps:print('EXAMPLE',json.dumps(dict(band=band,pattern=pat,odds_bin=labels[b],hits=count,opportunities=opps,frequency=count/opps,wilson95=wilson(count,opps))),flush=True)
