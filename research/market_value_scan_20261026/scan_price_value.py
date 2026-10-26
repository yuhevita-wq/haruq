import argparse,collections,csv,gzip,hashlib,itertools,json,math
from pathlib import Path
import numpy as np

parser=argparse.ArgumentParser()
for name in ['records','exacta','trifecta','output']:parser.add_argument('--'+name,type=Path,required=True)
args=parser.parse_args();OUT=args.output;plan=json.load(open(OUT/'analysis_plan.json'))
records={r['race_id']:r for r in csv.DictReader(args.records.open()) if '2025-07-01'<=r['date']<'2026-07-01'}
assert all(r['model_sha256']==plan['model_sha256'] for r in records.values())
with gzip.open(args.exacta,'rt') as f:exacta=json.load(f)
with gzip.open(args.trifecta,'rt') as f:common={json.loads(line)['race_id'] for line in f}&records.keys()&exacta.keys()
assert len(common)==21311
days=sorted({records[rid]['date'] for rid in common});dayidx={d:i for i,d in enumerate(days)}
limits=np.array(plan['reporting_bins_upper'],dtype=float)
labels=['(0,4]','(4,10]','(10,20]','(20,50]','(50,100]','(100,200]','(200,500]','(500,1000]','(1000,infinity)']
perms={(n,m):list(itertools.permutations(range(1,n+1),2 if m=='exacta' else 3)) for n in range(5,10) for m in ['exacta','trifecta']}
lookup={key:{p:i for i,p in enumerate(ps)} for key,ps in perms.items()}
den={};hits={};paid={};maxpay={};pool={};scopes=['all','HIGH_MEDplus_MED','LOW_control']
group_races=collections.Counter();seen=set();validation=collections.Counter();quotes_by_phase=collections.Counter()
def half(day):return 'early_2025H2' if day<'2026-01-01' else 'later_2026H1'
def groups(r,n,market):
    yield (half(r['date']),'exacta_band',r['exacta_band'],n,market)
    if market=='trifecta':yield (half(r['date']),'trifecta_band',r['trifecta_band'],n,market)
def scope_for(r):return 'LOW_control' if r['exacta_band']=='LOW' else 'HIGH_MEDplus_MED'
def arrays(book,r,market):
    n=int(r['rider_count']);bs=list(map(int,r['ranked_bikes'].split('>')));ps=perms[(n,market)]
    q=book['odds']
    keys=['-'.join(str(bs[i-1]) for i in p) for p in ps]
    assert set(keys)==set(q)
    values=[q[key][0] if market=='exacta' else q[key] for key in keys]
    if market=='exacta':assert all(len(set(q[key]))==1 for key in keys)
    values=np.asarray(values,dtype=float);assert np.isfinite(values).all() and (values>=1).all()
    bins=np.searchsorted(limits,values,side='left')
    w=lookup[(n,market)][tuple(map(int,r[market+'_rank_pattern'].split('>')))]
    assert abs(values[w]*100-float(r[market+'_payout_yen_per_100']))<1e-5
    return values,bins,w
def update(book,r,market):
    n=int(r['rider_count']);values,bins,w=arrays(book,r,market);ix=np.arange(len(values));di=dayidx[r['date']]
    for group in groups(r,n,market):
        if group not in den:
            den[group]=np.zeros((len(values),len(labels)),dtype=np.int64);hits[group]=np.zeros_like(den[group]);paid[group]=np.zeros_like(den[group],dtype=float);maxpay[group]=np.zeros_like(den[group],dtype=float)
        den[group][ix,bins]+=1;hits[group][w,bins[w]]+=1;paid[group][w,bins[w]]+=values[w];maxpay[group][w,bins[w]]=max(maxpay[group][w,bins[w]],values[w]);group_races[group]+=1
    hist=np.bincount(bins,minlength=len(labels))
    for scope in ['all',scope_for(r)]:
        for b in range(len(labels)):
            key=(scope,market,b)
            if key not in pool:pool[key]=np.zeros((len(days),3),dtype=float)
            pool[key][di,0]+=hist[b]
        pool[(scope,market,int(bins[w]))][di,1]+=values[w];pool[(scope,market,int(bins[w]))][di,2]+=1
    validation[market+'_payouts']+=1;quotes_by_phase[(half(r['date']),market)]+=len(values)
with gzip.open(args.trifecta,'rt') as f:
    for line in f:
        tri=json.loads(line);rid=tri['race_id']
        if rid not in common:continue
        assert rid not in seen;seen.add(rid);r=records[rid]
        update(exacta[rid],r,'exacta');update(tri,r,'trifecta')
assert seen==common
print('FULL_UNIVERSE_AGGREGATED',len(seen),dict(validation),flush=True)

def write(name,rs):
    with (OUT/name).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
def cell(group,i,b):
    if group not in den:return dict(opportunities=0,hits=0,return_units=0.,roi_pct=None,largest_single_win_share=None)
    N=int(den[group][i,b]);K=int(hits[group][i,b]);R=float(paid[group][i,b]);M=float(maxpay[group][i,b])
    return dict(opportunities=N,hits=K,return_units=R,roi_pct=100*R/N if N else None,largest_single_win_share=M/R if R else None)
both_rows=[];early_masks={};counts=collections.defaultdict(collections.Counter)
for base in sorted({g[1:] for g in den}):
    scheme,band,n,market=base;early=('early_2025H2',)+base;later=('later_2026H1',)+base
    shape=(len(perms[(n,market)]),len(labels));mask=np.zeros(shape,dtype=bool)
    for i,p in enumerate(perms[(n,market)]):
        for b,label in enumerate(labels):
            a=cell(early,i,b);z=cell(later,i,b)
            if not a['opportunities'] and not z['opportunities']:continue
            earlypos=a['opportunities']>0 and a['return_units']>a['opportunities'];laterpos=z['opportunities']>0 and z['return_units']>z['opportunities']
            mask[i,b]=earlypos
            row=dict(band_scheme=scheme,band=band,rider_count=n,market=market,rank_pattern='>'.join(map(str,p)),odds_bin=label)
            row.update({'early_'+k:v for k,v in a.items()});row.update({'later_'+k:v for k,v in z.items()})
            row.update(early_positive=earlypos,later_positive=laterpos,both_positive=earlypos and laterpos)
            both_rows.append(row)
            c=counts[(scheme,market)];c['cells']+=1;c['early_positive']+=earlypos;c['later_positive']+=laterpos;c['both_positive']+=earlypos and laterpos;c['supported_both_halves']+=a['opportunities']>0 and z['opportunities']>0
    early_masks[base]=mask
write('all_pattern_price_temporal_comparison.csv',both_rows)

# Persistence diagnostic: the later mask is fixed ONLY by early-period observed ROI>100%.
diagnostic={};control_races=collections.Counter();selected_races=collections.Counter()
def add_diag(scope,market,di,N,R,K):
    key=(scope,market)
    if key not in diagnostic:diagnostic[key]=np.zeros((len(days),3),dtype=float)
    diagnostic[key][di]+=[N,R,K]
with gzip.open(args.trifecta,'rt') as f:
    for line in f:
        tri=json.loads(line);rid=tri['race_id']
        if rid not in common:continue
        r=records[rid];n=int(r['rider_count']);di=dayidx[r['date']];book_by_market={'exacta':exacta[rid],'trifecta':tri};temporary={}
        for market in ['exacta','trifecta']:
            values,bins,w=arrays(book_by_market[market],r,market);temporary[market]=(values,bins,w)
            mask=early_masks[('exacta_band',r['exacta_band'],n,market)];picked=mask[np.arange(len(values)),bins]
            N=int(picked.sum());K=int(picked[w]);R=float(values[w]) if K else 0.
            for scope in ['early_positive_all']+(['early_positive_HIGH_MEDplus_MED'] if r['exacta_band']!='LOW' else []):
                add_diag(scope,market,di,N,R,K);add_diag(scope,'combined',di,N,R,K)
                selected_races[(scope,half(r['date']),market)]+=N>0
        if float(r['score_gap'])<1:continue
        bs=list(map(int,r['ranked_bikes'].split('>')))
        exq=exacta[rid]['odds'];original_ex=[(1,j) for j in range(2,6)]
        ex_values=[float(exq[f'{bs[0]}-{bs[j-1]}'][0]) for _,j in original_ex]
        if min(ex_values)<=4:continue
        for market,tickets in [('exacta',original_ex),('trifecta',[(1,j,k) for j,k in itertools.permutations(range(2,5),2)] if float(r['score_gap'])>=2 else [])]:
            if not tickets:continue
            actual=tuple(map(int,r[market+'_rank_pattern'].split('>')));K=int(actual in tickets);values,bins,w=temporary[market]
            add_diag('unchanged_control',market,di,len(tickets),float(values[w]) if K else 0.,K);add_diag('unchanged_control','combined',di,len(tickets),float(values[w]) if K else 0.,K)
        control_races[half(r['date'])]+=1

# Day-block intervals: same day weights applied to every price group and diagnostic.
rng=np.random.default_rng(20261026);weights={}
for ph in ['early_2025H2','later_2026H1']:
    ix=np.array([i for i,d in enumerate(days) if half(d)==ph]);D=len(ix);W=rng.multinomial(D,np.ones(D)/D,size=5000)
    weights[ph]=(ix,W)
def stats(series,ph):
    ix,W=weights[ph];a=series[ix];N=float(a[:,0].sum());R=float(a[:,1].sum());K=int(a[:,2].sum())
    if not N:return dict(opportunities=0,hits=0,investment_yen=0,returned_yen=0,profit_yen=0,roi_pct=None,day_bootstrap95_lower=None,day_bootstrap95_upper=None,largest_day_return_share=None,top5_day_return_share=None,bootstrap_status='no_opportunities')
    ds=W@a[:,0];rs=W@a[:,1];valid=ds>0;boot=100*rs[valid]/ds[valid]
    return dict(opportunities=int(N),hits=K,investment_yen=int(round(N*100)),returned_yen=int(round(R*100)),profit_yen=int(round((R-N)*100)),roi_pct=100*R/N,
                day_bootstrap95_lower=float(np.quantile(boot,.025)) if R else None,day_bootstrap95_upper=float(np.quantile(boot,.975)) if R else None,
                largest_day_return_share=float(a[:,1].max()/R) if R else None,top5_day_return_share=float(np.sort(a[:,1])[-5:].sum()/R) if R else None,
                bootstrap_status='computed' if R else 'no_wins_degenerate_bootstrap_not_reported')
pooled=[]
for (scope,market,b),a in sorted(pool.items()):
    for ph in weights:pooled.append(dict(scope=scope,market=market,odds_bin=labels[b],period=ph,**stats(a,ph)))
write('pooled_price_band_returns.csv',pooled)
diag=[]
for (scope,market),a in sorted(diagnostic.items()):
    for ph in weights:diag.append(dict(diagnostic=scope,market=market,period=ph,**stats(a,ph)))
write('early_positive_persistence_diagnostic.csv',diag)
summary=dict(model=plan['model'],shared_races=len(common),shared_periods=dict(collections.Counter(half(records[rid]['date']) for rid in common)),
             day_counts={ph:len(ix) for ph,(ix,W) in weights.items()},candidate_quote_counts={str(k):v for k,v in quotes_by_phase.items()},
             payout_verification=dict(validation),pattern_cells=len(both_rows),cell_scan_counts={str(k):dict(v) for k,v in counts.items()},
             unchanged_control_races=dict(control_races),diagnostics=diag,production_changed=False,adopted_policy=False,
             input_sha256={name:hashlib.sha256(getattr(args,name).read_bytes()).hexdigest() for name in ['records','exacta','trifecta']},
             limitation='All periods previously viewed. Later evaluation here is a temporal persistence diagnostic, not a newly untouched test. Final odds only.')
# Report sparsity without choosing a new minimum-size threshold.
for market in ['exacta','trifecta']:
    rs=[r for r in both_rows if r['band_scheme']=='exacta_band' and r['market']==market and r['both_positive']]
    summary.setdefault('both_positive_cell_sparsity',{})[market]=dict(cells=len(rs),median_early_hits=float(np.median([r['early_hits'] for r in rs])) if rs else None,median_later_hits=float(np.median([r['later_hits'] for r in rs])) if rs else None,median_early_largest_win_share=float(np.median([r['early_largest_single_win_share'] for r in rs])) if rs else None,median_later_largest_win_share=float(np.median([r['later_largest_single_win_share'] for r in rs])) if rs else None)
control=[r for r in diag if r['diagnostic']=='unchanged_control' and r['market']=='combined']
assert sum(r['investment_yen'] for r in control)==318000
assert sum(r['returned_yen'] for r in control)==266350
assert sum(control_races.values())==762
summary['output_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('*.csv')}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print('SCAN_COMPLETE',json.dumps({k:summary[k] for k in ['shared_races','shared_periods','candidate_quote_counts','pattern_cells','cell_scan_counts','both_positive_cell_sparsity']},ensure_ascii=False),flush=True)
print('DIAGNOSTICS',json.dumps(diag,ensure_ascii=False),flush=True)
