"""Empirical descriptive frequency estimation. Does not change any betting policy."""
import argparse,collections,csv,decimal,gzip,hashlib,itertools,json,math
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--records',type=Path,required=True)
parser.add_argument('--books',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
OUT=args.output;OUT.mkdir(parents=True,exist_ok=True)
RECORDS=args.records;BOOKS=args.books
plan=json.load(open(OUT/'estimation_plan.json'))
rows=list(csv.DictReader(RECORDS.open()))
assert len(rows)==plan['source_records'] and len({r['race_id'] for r in rows})==len(rows)
assert all(r['model']==plan['model'] and r['outcome_status']=='ok' for r in rows)
for r in rows:r['rider_count']=int(r['rider_count'])

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def period(day):
    if day<'2026-01-01':return '2025H2'
    if day<'2026-07-01':return '2026H1'
    if day<'2026-10-01':return '2026Q3'
    return '2026Oct01_22'
def wilson(k,n):
    assert 0<=k<=n and n>0
    z=1.959963984540054;p=k/n;d=1+z*z/n
    centre=(p+z*z/(2*n))/d
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return max(0.,centre-half),min(1.,centre+half)
def estimate(k,n):
    lo,hi=wilson(k,n)
    return dict(hits=k,opportunities=n,frequency=k/n,wilson95_lower=lo,wilson95_upper=hi)
def write(name,rs):
    with (OUT/name).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)

den=collections.Counter();hits=collections.Counter()
for r in rows:
    for scheme,band,markets in [('exacta_band',r['exacta_band'],['exacta','trifecta']),('trifecta_band',r['trifecta_band'],['trifecta'])]:
        for market in markets:
            pat=r[market+'_rank_pattern']
            for ph in ['all_20250701_20261022',period(r['date'])]:
                key=(ph,scheme,band,r['rider_count'],market)
                den[key]+=1;hits[key+(pat,)]+=1
base=[]
for key,n in sorted(den.items()):
    ph,scheme,band,nr,market=key
    for pattern in itertools.permutations(range(1,nr+1),2 if market=='exacta' else 3):
        pat='>'.join(map(str,pattern));k=hits[key+(pat,)]
        base.append(dict(period=ph,band_scheme=scheme,band=band,rider_count=nr,market=market,rank_pattern=pat,**estimate(k,n)))
    assert sum(v for (*prefix,_),v in hits.items() if tuple(prefix)==key)==n
write('rank_pattern_frequency_estimates.csv',base)
print('BASE_ESTIMATES',len(base),flush=True)

with gzip.open(BOOKS,'rt') as f:books=json.load(f)
bins=[decimal.Decimal(str(v)) for v in [4,10,20,50,100]]
labels=['(0,4]','(4,10]','(10,20]','(20,50]','(50,100]','(100,infinity)']
price_den=collections.Counter();price_hits=collections.Counter();quote_sum=collections.Counter();quote_min={};quote_max={}
coverage=collections.Counter();problems=[];matched_ids=[];ticket_opportunities=0;payout_checks=0
for r in rows:
    if not ('2025-07-01'<=r['date']<'2026-07-01'):continue
    ph=period(r['date']);nr=r['rider_count'];band=r['exacta_band'];coverage[(ph,band,nr,'eligible')]+=1
    book=books.get(r['race_id'])
    if book is None:
        coverage[(ph,band,nr,'missing')]+=1;continue
    bikes=list(map(int,r['ranked_bikes'].split('>')))
    expected={f'{a}-{b}' for a,b in itertools.permutations(bikes,2)}
    quotes={}
    try:
        assert set(book['odds'])==expected,'incomplete_bike_pair_set'
        for pair,values in book['odds'].items():
            unique={decimal.Decimal(v) for v in values}
            assert len(unique)==1,'conflicting_quote'
            v=unique.pop();assert v.is_finite() and v>0,'invalid_quote';quotes[pair]=v
        winning=f"{r['actual_first_bike']}-{r['actual_second_bike']}"
        assert r['exacta_payout_verified']=='True' and quotes[winning]*100==decimal.Decimal(r['exacta_payout_yen_per_100']),'winning_payout_mismatch'
    except (AssertionError,decimal.InvalidOperation,KeyError) as e:
        coverage[(ph,band,nr,'invalid')]+=1;problems.append(dict(race_id=r['race_id'],reason=str(e)));continue
    coverage[(ph,band,nr,'matched')]+=1;matched_ids.append(r['race_id']);payout_checks+=1
    winner=r['exacta_rank_pattern']
    for i,j in itertools.permutations(range(1,nr+1),2):
        pattern=f'{i}>{j}';value=quotes[f'{bikes[i-1]}-{bikes[j-1]}']
        bucket=next((k for k,b in enumerate(bins) if value<=b),5)
        ticket_opportunities+=1
        for time in ['all_20250701_20260630',ph]:
            key=(time,band,nr,pattern,bucket);price_den[key]+=1;price_hits[key]+=pattern==winner
            f=float(value);quote_sum[key]+=f;quote_min[key]=min(quote_min.get(key,f),f);quote_max[key]=max(quote_max.get(key,f),f)
conditional=[]
for key,n in sorted(price_den.items()):
    ph,band,nr,pat,bucket=key
    conditional.append(dict(period=ph,band_scheme='exacta_band',band=band,rider_count=nr,market='exacta',rank_pattern=pat,
                            odds_bin=labels[bucket],mean_quoted_odds=quote_sum[key]/n,min_quoted_odds=quote_min[key],max_quoted_odds=quote_max[key],
                            **estimate(price_hits[key],n)))
write('exacta_price_conditional_frequencies.csv',conditional)
cov=[]
for ph,band,nr in sorted({k[:3] for k in coverage}):
    d={status:coverage[(ph,band,nr,status)] for status in ['eligible','matched','missing','invalid']}
    assert d['eligible']==d['matched']+d['missing']+d['invalid']
    cov.append(dict(period=ph,band=band,rider_count=nr,**d))
write('price_coverage.csv',cov)
assert sum(price_hits[k] for k in price_den if k[0]=='all_20250701_20260630')==len(matched_ids)

# Independent reconstruction of existing pattern counts, excluding zero-count cells.
old=list(csv.DictReader((RECORDS.parent/'rank_pattern_counts.csv').open()))
for r in old:
    if r['phase']!='all_recorded_periods':continue
    key=('all_20250701_20261022',r['market']+'_band',r['band'],int(r['rider_count']),r['market'])
    assert hits[key+(r['rank_pattern'],)]==int(r['count'])
    assert den[key]==int(r['group_races'])
matched_id_set=set(matched_ids)
summary=dict(model=plan['model'],records=len(rows),input_sha256=dict(records=digest(RECORDS),books=digest(BOOKS)),
             base_estimate_cells=len(base),base_zero_hit_cells=sum(r['hits']==0 for r in base),
             conditional_estimate_cells=len(conditional),price_matched_races=len(matched_ids),
             price_eligible_races=sum(r['eligible'] for r in cov),price_missing_races=sum(r['missing'] for r in cov),
             price_invalid_races=sum(r['invalid'] for r in cov),price_ticket_opportunities=ticket_opportunities,
             payout_checks=payout_checks,price_problems=problems,production_changed=False,selection_performed=False,
             interval='95% Wilson approximate independent-binomial interval; no adjustment for day clustering, drift or prior research selection',
             record_periods=dict(collections.Counter(period(r['date']) for r in rows)),
             price_periods=dict(collections.Counter(period(r['date']) for r in rows if r['race_id'] in matched_id_set)))
summary['output_sha256']={p.name:digest(p) for p in OUT.glob('*.csv')}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print('SUMMARY',json.dumps(summary,ensure_ascii=False),flush=True)
for market,pattern in [('exacta','1>2'),('exacta','2>1'),('exacta','4>2'),('trifecta','1>2>3'),('trifecta','4>2>1')]:
    for band in ['HIGH','MED+','MED']:
        found=[x for x in base if x['period']=='all_20250701_20261022' and x['band_scheme']=='exacta_band' and x['band']==band and x['rider_count']==7 and x['market']==market and x['rank_pattern']==pattern]
        print('ILLUSTRATION',json.dumps(found[0],ensure_ascii=False))
for band in ['HIGH','MED+','MED']:
    for r in conditional:
        if r['period']=='all_20250701_20260630' and r['rider_count']==7 and r['band']==band and r['rank_pattern']=='1>2':
            print('PRICE_ILLUSTRATION',json.dumps(r,ensure_ascii=False))
