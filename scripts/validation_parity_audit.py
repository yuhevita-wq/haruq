"""Read-only audit: never trains, changes policies or writes public forecasts."""
import collections,csv,hashlib,itertools,json,math,sqlite3,sys
from pathlib import Path
import numpy as np
import pandas as pd
from config import DB_PATH,CLASS_MAP
from features.builder import FeatureBuilder
from models.lgbm_ranker import LGBMRanker
from scripts.reproduce_haruqube_fresh import dataset,split,VALID_END,TEST_END
from scripts.reproduce_haruqube_20260321 import verify_sources,settle,simulate
import scripts.reproduce_haruqube_20260321 as repro
from scripts.audit_haruq_grade_inclusion import ledger_check

OUT=Path('validation_audit');OUT.mkdir(exist_ok=True)
MODEL='flagship_inputs/haruqube_20260321_fresh_model.pkl'
SHA='e70690f4538b77e927a042e7ae2db312f8a0a4f16bf72def37e7ccad3568c193'
assert hashlib.sha256(Path(MODEL).read_bytes()).hexdigest()==SHA
verify_sources()
model=LGBMRanker();model.load(MODEL)
builder=FeatureBuilder()
frame,features,valid=dataset()
con=sqlite3.connect(DB_PATH);con.row_factory=sqlite3.Row
pay=pd.read_sql_query('SELECT race_id,sanrentan_combo,sanrentan_payout FROM race_payouts',con)
frame=frame.merge(pay,on='race_id',how='left',validate='many_to_one')
test=frame[(frame.race_date>=VALID_END)&(frame.race_date<TEST_END)]
test,_,_,_=split(test,features)
assert features==model.feature_names
repro.OUT=OUT
simulate(test,model,features)
archived=list(csv.DictReader(open('flagship_inputs/holdout_all_selected_tickets.csv')))
rebuilt=list(csv.DictReader(open(OUT/'holdout_all_selected_tickets.csv')))
baseline_check=ledger_check(rebuilt,archived)
print('BASELINE_LEDGER_REPRODUCED',baseline_check,flush=True)
test['audit_score']=model.predict(test[features].apply(pd.to_numeric,errors='coerce').fillna(0)).values

def summary(rows):
 n=len(rows);stake=sum(r['stake'] for r in rows);paid=sum(r['paid'] for r in rows)
 return dict(races=n,stake=stake,paid=paid,profit=paid-stake,roi_pct=100*paid/stake if stake else None,hits=sum(r['paid']>0 for r in rows))
def jsonsave(name,value):
 (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=lambda v:v.item() if hasattr(v,'item') else str(v))+'\n')
def tickets(bikes,gap):
 ex=[f'{bikes[0]}>{b}' for b in bikes[1:5]] if gap>=1 else []
 tri=[f'{bikes[0]}>{b}>{c}' for b,c in itertools.permutations(bikes[1:4],2)] if gap>=2 else []
 return ex,tri
def rejected(group):
 cls=[str(x).upper() for x in group['class']]
 return all(x in ('0','0.0','NONE','NAN','') for x in cls) or any(x.startswith('L') or x.startswith('Ｌ') for x in cls)

rows=[];excluded=collections.Counter();all_groups={}
for rid,g in test.groupby('race_id',sort=False):
 all_groups[str(rid)]=g
 if rejected(g):excluded[str(g.iloc[0]['grade'])]+=1;continue
 ranked=g.sort_values(['audit_score','bike_number'],ascending=[False,True],kind='stable')
 gap=float(ranked.iloc[0].audit_score-ranked.iloc[1].audit_score)
 if gap<1:continue
 bikes=list(map(int,ranked.bike_number));ex,tri=tickets(bikes,gap)
 actual=g.sort_values('finish_position',kind='stable');a2=tuple(map(int,actual.head(2).bike_number));a3=tuple(map(int,actual.head(3).bike_number))
 markets=[]
 for key,ts,ac,prefix in [('exacta',ex,a2,'nisyatan'),('trifecta',tri,a3,'sanrentan')]:
  if not ts:continue
  z=settle('current_'+key,ranked,gap,str(ranked.iloc[0].grade),'HIGH',500,[tuple(map(int,t.split('>'))) for t in ts],ac,prefix)
  markets.append(dict(market=key,stake=int(z['invested_yen']),paid=int(z['returned_yen']),verified=bool(z['payout_verified']),tickets=ts,actual=z['winning_combo']))
 if not all(m['verified'] for m in markets):
  excluded['unverified_payout']+=1;continue
 rid=str(rid)
 rows.append(dict(race_id=rid,date=str(ranked.iloc[0].race_date),grade=str(ranked.iloc[0].grade),venue=rid[8:10],gap=gap,stake=sum(m['stake'] for m in markets),paid=sum(m['paid'] for m in markets),markets=markets))
rows.sort(key=lambda r:(r['date'],r['race_id']))
jsonsave('current_policy_ledger.json',rows)
with open(OUT/'current_policy_ledger.csv','w') as f:
 w=csv.DictWriter(f,fieldnames=['race_id','date','grade','gap','stake','paid','profit','markets']);w.writeheader()
 for r in rows:w.writerow({k:(r['paid']-r['stake'] if k=='profit' else json.dumps(r['markets'],ensure_ascii=False) if k=='markets' else r[k]) for k in w.fieldnames})

today=json.loads(Path('docs/haruq/days/20261025.json').read_text())
today_buy=[r for r in today['records'] if r.get('prediction',{}).get('total_yen',0)>0]
today_checks=[]
for r in today['records']:
 if r['status']!='predicted':continue
 p=r['prediction'];rank=sorted(p['ranked'],key=lambda x:x['rank']);bikes=[int(x['bike']) for x in rank]
 gap=p['confidence'];ex,tri=tickets(bikes,gap)
 actual_ex=p['bets']['exacta'];actual_tri=p['bets']['trifecta']
 today_checks.append(dict(race_id=r['race_id'],model_match=p['model_sha256']==SHA,exacta_match=ex==actual_ex['tickets'],trifecta_match=tri==actual_tri['tickets'],stake_match=p['total_yen']==500*(len(ex)+len(tri)),before_start=p.get('status')=='発走前',history=p.get('history'),run=p.get('web_record',{}).get('run_id')))
jsonsave('today_policy_checks.json',today_checks)

# Feature parity is a matched archived-input diagnostic, not proof of timestamped pre-race inputs.
# Roll back every master-class substitution, so no historical input asset is changed.
keys=sorted(all_groups)
sample_ids=sorted(set(keys[int(i)] for i in np.linspace(0,len(keys)-1,240)))
mismatch=collections.Counter();compared=collections.Counter();deltas=collections.defaultdict(list);parity=[]
for j,rid in enumerate(sample_ids):
 g=all_groups[rid];con.execute('SAVEPOINT parity')
 try:
  for _,r in g.iterrows():con.execute('UPDATE riders SET class=? WHERE rider_id=?',(str(r['class']) if str(r['class']) not in ('0','0.0') else None,str(r['rider_id'])))
  online=builder.build_race_features(rid,str(g.iloc[0].race_date),con)
  if online.empty:parity.append(dict(race_id=rid,error='no entries'));continue
  a=g.set_index(g.rider_id.astype(str));b=online.set_index(online.rider_id.astype(str))
  if set(a.index)!=set(b.index):parity.append(dict(race_id=rid,error='rider sets differ',batch=len(a),online=len(b)));continue
  b=b.loc[a.index];aa=a[features].apply(pd.to_numeric,errors='coerce').fillna(0);bb=b.reindex(columns=features).apply(pd.to_numeric,errors='coerce').fillna(0)
  changed=[]
  for name in features:
   diff=np.abs(aa[name].to_numpy()-bb[name].to_numpy());bad=~np.isclose(aa[name],bb[name],rtol=1e-8,atol=1e-8)
   mismatch[name]+=int(bad.sum());compared[name]+=len(a);deltas[name].extend(diff.tolist())
   if bad.any():changed.append(name)
  sb=model.predict(bb).values;sa=a.audit_score.to_numpy()
  ba=a.bike_number.astype(int).to_numpy();oa=np.lexsort((ba,-sa));ob=np.lexsort((ba,-sb))
  ga=float(sa[oa[0]]-sa[oa[1]]);gb=float(sb[ob[0]]-sb[ob[1]])
  ta=tickets(ba[oa].tolist(),ga);tb=tickets(ba[ob].tolist(),gb)
  parity.append(dict(race_id=rid,riders=len(a),mismatched_features=changed,feature_identical=not changed,top1_match=int(ba[oa[0]])==int(ba[ob[0]]),order_match=ba[oa].tolist()==ba[ob].tolist(),batch_gap=ga,online_gap=gb,buy_match=(ga>=1)==(gb>=1),trifecta_buy_match=(ga>=2)==(gb>=2),tickets_match=ta==tb,max_score_delta=float(np.max(np.abs(sa-sb)))))
 finally:con.execute('ROLLBACK TO parity');con.execute('RELEASE parity')
 if j%40==0:print('PARITY_PROGRESS',j,len(sample_ids),flush=True)
jsonsave('feature_parity_races.json',parity)
feature_stats=[dict(feature=n,mismatched_cells=mismatch[n],compared_cells=compared[n],mismatch_pct=100*mismatch[n]/compared[n] if compared[n] else None,max_abs_delta=max(deltas[n]) if deltas[n] else None,mean_abs_delta=float(np.mean(deltas[n])) if deltas[n] else None) for n in features]
jsonsave('feature_parity_features.json',feature_stats)
valid_parity=[p for p in parity if 'error' not in p]

loss=-18050;roi=26950/45000
def windows(source,stride=1):
 arr=[]
 for i in range(0,len(source)-20,stride):
  z=source[i:i+21];st=sum(r['stake'] for r in z);pa=sum(r['paid'] for r in z)
  arr.append(dict(start=z[0]['race_id'],end=z[-1]['race_id'],stake=st,paid=pa,profit=pa-st,roi=pa/st,trifecta_races=sum(len(r['markets'])==2 for r in z)))
 return arr
def window_stats(a):
 if not a:return dict(windows=0)
 v=np.array([r['roi'] for r in a]);p=np.array([r['profit'] for r in a])
 return dict(windows=len(a),roi_at_or_below_today=int((v<=roi+1e-12).sum()),roi_at_or_below_today_pct=float(np.mean(v<=roi+1e-12)*100),loss_at_least_today=int((p<=loss).sum()),loss_at_least_today_pct=float(np.mean(p<=loss)*100),roi_percentiles={str(q):float(np.percentile(v,q)*100) for q in [0,1,5,10,25,50,75,90,95,99,100]})
sliding=windows(rows);blocks=windows(rows,21)
same_mix=[w for w in sliding if w['trifecta_races']==1]
by_type=collections.defaultdict(list)
for r in rows:by_type[(r['grade'],len(r['markets']))].append(r)
today_mix=collections.Counter((r['prediction']['grade'],sum(v['points']>0 for v in r['prediction']['bets'].values())) for r in today_buy)
rng=np.random.default_rng(20261025);draws=50000;bootpaid=np.zeros(draws);bootstake=np.zeros(draws)
for k,n in today_mix.items():
 pool=by_type[k];ix=rng.integers(0,len(pool),size=(draws,n));pa=np.array([r['paid'] for r in pool]);st=np.array([r['stake'] for r in pool]);bootpaid+=pa[ix].sum(axis=1);bootstake+=st[ix].sum(axis=1)
boot=dict(method='Independent empirical resampling by grade and exacta-only/exacta+trifecta; descriptive under archived backtest, not live risk estimate',draws=draws,seed=20261025,today_mix={str(k):v for k,v in today_mix.items()},pool_sizes={str(k):len(by_type[k]) for k in today_mix},stake_unique=np.unique(bootstake).tolist(),roi_at_or_below_today_pct=float(np.mean(bootpaid/bootstake<=roi+1e-12)*100),loss_at_least_today_pct=float(np.mean(bootpaid-bootstake<=loss)*100),profit_percentiles={str(q):float(np.percentile(bootpaid-bootstake,q)) for q in [0,1,5,10,25,50,75,95,99,100]})
def concentration(rr):
 total=summary(rr);s=sorted(rr,key=lambda r:r['paid'],reverse=True);paid=total['paid'];res=[]
 for n in sorted(set([1,3,5,10,20,max(1,math.ceil(len(rr)*.01)),max(1,math.ceil(len(rr)*.05)),max(1,math.ceil(len(rr)*.1))])):
  if n>=len(rr):continue
  removed=sum(r['paid'] for r in s[:n]);remaining=summary(s[n:]);res.append(dict(remove_top=n,share_of_returns_pct=100*removed/paid if paid else None,remaining=remaining,roi_if_winnings_zero_but_stakes_retained_pct=100*(paid-removed)/total['stake']))
 acc=0;break_even_remove=None
 for i,r in enumerate(s,1):
  acc+=r['paid']-r['stake']
  if total['profit']-acc<=0:break_even_remove=i;break
 return dict(total=total,stress=res,minimum_largest_return_races_removed_to_erase_profit=break_even_remove)
def segments(rr,key):
 g=collections.defaultdict(list)
 for r in rr:g[key(r)].append(r)
 return {k:summary(v) for k,v in sorted(g.items())}
market_rows={k:[dict(r,stake=m['stake'],paid=m['paid']) for r in rows for m in r['markets'] if m['market']==k] for k in ['exacta','trifecta']}
data=dict(model_sha256=SHA,baseline_ledger_check=baseline_check,holdout_races=len(all_groups),current_policy=summary(rows),excluded=dict(excluded),today_policy=dict(predicted=len(today_checks),purchases=len(today_buy),all_model_match=all(r['model_match'] for r in today_checks),all_tickets_match=all(r['exacta_match'] and r['trifecta_match'] for r in today_checks),all_stakes_match=all(r['stake_match'] for r in today_checks),all_published_before_start=all(r['before_start'] for r in today_checks)),parity=dict(requested=len(sample_ids),compared=len(valid_parity),feature_identical_races=sum(r['feature_identical'] for r in valid_parity),top1_match_races=sum(r['top1_match'] for r in valid_parity),buy_match_races=sum(r['buy_match'] for r in valid_parity),trifecta_buy_match_races=sum(r['trifecta_buy_match'] for r in valid_parity),tickets_match_races=sum(r['tickets_match'] for r in valid_parity),mismatch_features=sorted(feature_stats,key=lambda x:-(x['mismatch_pct'] or 0)),scope='Matched historical archive entries, master class aligned to contemporaneous result in rolled-back transactions; not timestamp proof'),downside=dict(observed=dict(races=21,stake=45000,paid=26950,loss=loss,roi_pct=100*roi),sliding=window_stats(sliding),nonoverlapping=window_stats(blocks),sliding_same_21_exacta_plus_1_trifecta=window_stats(same_mix),matched_resampling=boot,overlapping_windows_are_not_independent=True),concentration=dict(combined=concentration(rows),markets={k:concentration(v) for k,v in market_rows.items()}),segments=dict(grade=segments(rows,lambda r:r['grade']),year=segments(rows,lambda r:r['date'][:4]),month=segments(rows,lambda r:r['date'][:7]),venue=segments(rows,lambda r:r['venue'])),limitations=['Historical feature timestamps unavailable; source-line metadata in batch comes from race_results while online uses entries.','Exact historic live entry snapshots unavailable, so archive-input parity cannot establish true live ROI.','Current HIGH-only policy was chosen after viewing holdout; selection bias remains.','21-race windows are consecutive by date and race ID, not actual interleaved start time.','Current odds and popularity are calculated as unused columns but are NOT in the actual 44 model features.'])
jsonsave('audit_summary.json',data)
print('VALIDATION_AUDIT_COMPLETE',json.dumps({k:data[k] for k in ['current_policy','today_policy','parity','downside']},ensure_ascii=False),flush=True)
