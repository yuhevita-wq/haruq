import argparse,collections,csv,gzip,hashlib,itertools,json,math
from pathlib import Path
import numpy as np
parser=argparse.ArgumentParser()
for name in ['records','exacta','trifecta','output']:parser.add_argument('--'+name,type=Path,required=True)
args=parser.parse_args();P=args.output
source=list(csv.DictReader((P/'all_pattern_price_temporal_comparison.csv').open()))
grouped={}
for r in source:
    key=tuple(r[x] for x in ['band_scheme','band','rider_count','market'])+('>'.join(map(str,sorted(map(int,r['rank_pattern'].split('>'))))),r['odds_bin'])
    a=grouped.setdefault(key,dict(early_N=0,later_N=0,early_K=0,later_K=0,early_yen=0,later_yen=0))
    for ph in ['early','later']:
        a[ph+'_N']+=int(r[ph+'_opportunities']);a[ph+'_K']+=int(r[ph+'_hits']);a[ph+'_yen']+=int(round(float(r[ph+'_return_units'])*100))
out=[];selected=set()
for key,a in sorted(grouped.items()):
    scheme,band,n,market,members,price=key
    earlypos=a['early_N']>0 and a['early_yen']>a['early_N']*100
    laterpos=a['later_N']>0 and a['later_yen']>a['later_N']*100
    if earlypos and scheme=='exacta_band':selected.add(key)
    out.append(dict(band_scheme=scheme,band=band,rider_count=n,market=market,unordered_members=members,odds_bin=price,**a,
                    early_roi_pct=a['early_yen']/a['early_N'] if a['early_N'] else None,later_roi_pct=a['later_yen']/a['later_N'] if a['later_N'] else None,
                    early_positive=earlypos,later_positive=laterpos,both_positive=earlypos and laterpos))
with (P/'all_unordered_member_set_temporal_comparison.csv').open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
records={r['race_id']:r for r in csv.DictReader(args.records.open()) if '2025-07-01'<=r['date']<'2026-07-01'}
with gzip.open(args.exacta,'rt') as f:ex=json.load(f)
with gzip.open(args.trifecta,'rt') as f:common={json.loads(line)['race_id'] for line in f}&records.keys()&ex.keys()
days=sorted({records[rid]['date'] for rid in common});idx={d:i for i,d in enumerate(days)}
limits=[4,10,20,50,100,200,500,1000];labels=['(0,4]','(4,10]','(10,20]','(20,50]','(50,100]','(100,200]','(200,500]','(500,1000]','(1000,infinity)']
perms={(n,m):list(itertools.permutations(range(1,n+1),2 if m=='exacta' else 3)) for n in range(5,10) for m in ['exacta','trifecta']}
members={key:['>'.join(map(str,sorted(p))) for p in ps] for key,ps in perms.items()}
daily={}
with gzip.open(args.trifecta,'rt') as f:
    for line in f:
        tri=json.loads(line);rid=tri['race_id']
        if rid not in common:continue
        r=records[rid];n=int(r['rider_count']);bikes=list(map(int,r['ranked_bikes'].split('>')));di=idx[r['date']]
        for market,book in [('exacta',ex[rid]),('trifecta',tri)]:
            ps=perms[(n,market)];q=book['odds'];K=0;N=0;R=0.
            actual=tuple(map(int,r[market+'_rank_pattern'].split('>')))
            for j,p in enumerate(ps):
                key='-'.join(str(bikes[i-1]) for i in p);value=float(q[key][0] if market=='exacta' else q[key]);b=next((i for i,v in enumerate(limits) if value<=v),8)
                group=('exacta_band',r['exacta_band'],str(n),market,members[(n,market)][j],labels[b])
                if group not in selected:continue
                N+=1
                if p==actual:K+=1;R+=value
            for scope in ['early_positive_unordered_all']+(['early_positive_unordered_HIGH_MEDplus_MED'] if r['exacta_band']!='LOW' else []):
                for market_key in [market,'combined']:
                    dest=daily.setdefault((scope,market_key),np.zeros((len(days),3),dtype=float));dest[di]+=[N,R,K]
rng=np.random.default_rng(20261026);diag=[]
for ph in ['early_2025H2','later_2026H1']:
    ix=np.array([i for i,d in enumerate(days) if (d<'2026-01-01')==(ph=='early_2025H2')]);D=len(ix);W=rng.multinomial(D,np.ones(D)/D,size=5000)
    for (scope,market),a in sorted(daily.items()):
        a=a[ix];N=float(a[:,0].sum());R=float(a[:,1].sum());K=int(a[:,2].sum());bd=W@a[:,0];br=W@a[:,1];v=bd>0;boot=br[v]/bd[v]*100
        diag.append(dict(diagnostic=scope,market=market,period=ph,opportunities=int(N),hits=K,investment_yen=int(round(N*100)),returned_yen=int(round(R*100)),roi_pct=R/N*100 if N else None,
                         day_bootstrap95_lower=float(np.quantile(boot,.025)) if len(boot) else None,day_bootstrap95_upper=float(np.quantile(boot,.975)) if len(boot) else None))
with (P/'unordered_member_set_persistence_diagnostic.csv').open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(diag[0]));w.writeheader();w.writerows(diag)
# Direct per-cell aggregation and independent price-book replay must agree.
for market in ['exacta','trifecta']:
    for ph in ['early','later']:
        cells=[r for r in out if r['band_scheme']=='exacta_band' and r['band']!='LOW' and r['market']==market and r['early_positive']]
        row=next(d for d in diag if d['diagnostic']=='early_positive_unordered_HIGH_MEDplus_MED' and d['market']==market and d['period']==('early_2025H2' if ph=='early' else 'later_2026H1'))
        assert row['opportunities']==sum(r[ph+'_N'] for r in cells)
        assert row['returned_yen']==sum(r[ph+'_yen'] for r in cells)
summary=dict(unordered_cells=len(out),diagnostics=diag,classification='Same primary exacta_band; all unordered sets include all2! or3! orders before selecting by early-period aggregate returns.',production_changed=False,adopted_policy=False,
             crosscheck='All selected HIGH/MED+/MED cell totals equal independent full-book replay.')
(P/'unordered_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False),flush=True)
