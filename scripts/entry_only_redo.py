"""Research-only entry-sourced replay and retraining. Never updates production."""
import collections,csv,hashlib,itertools,json,sqlite3,time
from pathlib import Path
import numpy as np
import pandas as pd
from config import DB_PATH,CLASS_MAP
from features.builder import FeatureBuilder
from models.lgbm_ranker import LGBMRanker
from scripts.reproduce_haruqube_fresh import dataset,split,TRAIN_END,VALID_END,TEST_END
from scripts.reproduce_haruqube_20260321 import verify_sources,settle

OUT=Path('entry_only_redo');OUT.mkdir(exist_ok=True)
MODEL='flagship_inputs/haruqube_20260321_fresh_model.pkl'
SHA='e70690f4538b77e927a042e7ae2db312f8a0a4f16bf72def37e7ccad3568c193'
def save(name,obj):
 (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=lambda x:x.item() if hasattr(x,'item') else str(x)))
def writecsv(name,rows):
 if not rows:return
 with (OUT/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def summary(rows):
 s=sum(x['stake'] for x in rows);p=sum(x['paid'] for x in rows)
 return dict(races=len(rows),stake=s,paid=p,profit=p-s,roi_pct=100*p/s if s else None,hits=sum(x['paid']>0 for x in rows))
def phase(d):return 'train' if d<TRAIN_END else 'validation' if d<VALID_END else 'holdout' if d<TEST_END else 'later'
def rejected(g):
 c=[str(x).upper() for x in g['class']]
 return all(x in ('0','0.0','NONE','NAN','') for x in c) or any(x.startswith(('L','Ｌ')) for x in c)
class Guard:
 """Reject all result queries except the original strictly past rider-history query."""
 def __init__(self,c,day):self.c=c;self.day=day
 def execute(self,q,p=()):
  if 'race_results' in q.lower():
   assert 'r.date < ?' in q and self.day in p and 'rr.rider_id = ?' in q,q
  return self.c.execute(q,p)

def predict_ledger(frame,model,features,label):
 frame=frame.copy();frame['score']=model.predict(frame[features].apply(pd.to_numeric,errors='coerce').fillna(0)).values
 rows=[];preds=[];excluded=collections.Counter()
 for rid,g in frame.groupby('race_id',sort=False):
  if rejected(g):excluded['girls_or_all_unknown_class']+=1;continue
  rank=g.sort_values(['score','bike_number'],ascending=[False,True],kind='stable');bs=rank.bike_number.astype(int).tolist();gap=float(rank.iloc[0].score-rank.iloc[1].score)
  ex=[(bs[0],b) for b in bs[1:5]] if gap>=1 else [];tri=[(bs[0],b,c) for b,c in itertools.permutations(bs[1:4],2)] if gap>=2 else []
  preds.append(dict(race_id=str(rid),date=str(rank.iloc[0].race_date),grade=str(rank.iloc[0].grade),gap=gap,ranked_bikes='>'.join(map(str,bs)),exacta_tickets=';'.join('>'.join(map(str,t)) for t in ex),trifecta_tickets=';'.join('>'.join(map(str,t)) for t in tri)))
  if not ex:continue
  actual=g.sort_values('finish_position',kind='stable');markets=[]
  for key,ts,n,prefix in [('exacta',ex,2,'nisyatan'),('trifecta',tri,3,'sanrentan')]:
   if not ts:continue
   ac=tuple(actual.head(n).bike_number.astype(int));z=settle(label,rank,gap,str(rank.iloc[0].grade),'HIGH',100,ts,ac,prefix)
   markets.append(dict(market=key,stake=int(z['invested_yen']),paid=int(z['returned_yen']),verified=bool(z['payout_verified']),tickets=['>'.join(map(str,t)) for t in ts],actual=z['winning_combo']))
  if not all(m['verified'] for m in markets):excluded['unverified_payout']+=1;continue
  rows.append(dict(race_id=str(rid),date=str(rank.iloc[0].race_date),grade=str(rank.iloc[0].grade),gap=gap,stake=sum(m['stake'] for m in markets),paid=sum(m['paid'] for m in markets),markets=markets))
 serial=[dict(r,markets=json.dumps(r['markets'],ensure_ascii=False),profit=r['paid']-r['stake']) for r in rows]
 writecsv(label+'_ledger.csv',serial);writecsv(label+'_predictions.csv',preds)
 return dict(combined=summary(rows),exacta=summary([dict(r,stake=m['stake'],paid=m['paid']) for r in rows for m in r['markets'] if m['market']=='exacta']),trifecta=summary([dict(r,stake=m['stake'],paid=m['paid']) for r in rows for m in r['markets'] if m['market']=='trifecta']),excluded=dict(excluded),months={d:summary([r for r in rows if r['date'].startswith(d)]) for d in sorted({r['date'][:7] for r in rows})})

def main():
 assert hashlib.sha256(Path(MODEL).read_bytes()).hexdigest()==SHA
 verify_sources();oldmodel=LGBMRanker();oldmodel.load(MODEL);builder=FeatureBuilder()
 old,features,_=dataset();assert features==oldmodel.feature_names
 con=sqlite3.connect(DB_PATH);con.row_factory=sqlite3.Row
 pay=pd.read_sql_query('SELECT race_id,sanrentan_combo,sanrentan_payout FROM race_payouts',con);old=old.merge(pay,on='race_id',how='left',validate='many_to_one')
 replacements=[];eligible=[];provenance=[];counts=collections.Counter();change=collections.defaultdict(collections.Counter)
 groups=list(old.groupby('race_id',sort=False))
 print('REBUILD_START',len(groups),flush=True)
 for j,(rid,g) in enumerate(groups):
  day=str(g.iloc[0].race_date);ph=phase(day)
  # Same query/order as frozen online line builder. No current outcome fields.
  entries=con.execute('SELECT * FROM entries WHERE race_id=?',(str(rid),)).fetchall();em={str(e['rider_id']):e for e in entries}
  if set(em)!=set(g.rider_id.astype(str)) or len(entries)!=len(g):counts[ph+'_incomplete_entries']+=1;continue
  if any(e['bike_number'] is None for e in entries) or len({e['bike_number'] for e in entries})!=len(entries):counts[ph+'_invalid_entry_bikes']+=1;continue
  lf=builder.line_builder._build_all(Guard(con,day),str(rid));rf=builder.race_builder.build_batch(str(rid),list(em),day,Guard(con,day))
  clean=[]
  for _,r in g.iterrows():
   k=str(r.rider_id);e=em[k];d=dict(race_id=str(rid),rider_id=r.rider_id,**lf[k],**rf[k]);d['class']=e['class'];d['rider_class_num']=float(CLASS_MAP.get(e['class'],6));d['bike_number']=int(e['bike_number']);d['frame_number']=e['frame_number'];d['line_group']=e['line_group'];d['line_role']=e['line_role'];
   if float(r['rider_race_count'])==0:d['rider_avg_margin']=0.0 # frozen online empty-history branch uses setdefault(0), unlike batch DEFAULT_AVG_MARGIN
   clean.append(d)
  c=pd.DataFrame(clean).set_index('rider_id');a=g.set_index('rider_id');a=a.loc[c.index]
  # Inputs not replaced here are strictly past-only history statistics from the original engine.
  c['class_rank_in_race']=c['rider_class_num'].rank(method='min');c['rider_class_x_jiku']=c['rider_class_num']*c['line_is_jiku'];c['form_trend_x_line_strength']=a['rider_form_trend']*c['line_strength_score']
  counts[ph+'_complete_entries']+=1;eligible.append(rid);replacements.extend(c.reset_index().to_dict('records'))
  if j%10000==0:print('REBUILD_PROGRESS',j,len(groups),flush=True)
 clean=old[old.race_id.isin(eligible)].copy();repl=pd.DataFrame(replacements);replace_cols=[c for c in repl if c not in ('race_id','rider_id')]
 clean=clean.drop(columns=[c for c in replace_cols if c in clean]);clean=clean.merge(repl,on=['race_id','rider_id'],validate='one_to_one')
 clean[features]=clean[features].apply(pd.to_numeric,errors='coerce').fillna(0)
 oldmatch=old[old.race_id.isin(eligible)].reset_index(drop=True);clean=clean.reset_index(drop=True)
 assert oldmatch[['race_id','rider_id']].equals(clean[['race_id','rider_id']])
 phases=clean.race_date.map(phase)
 for name in features:
  av=pd.to_numeric(oldmatch[name],errors='coerce').fillna(0).to_numpy();bv=clean[name].to_numpy();badcells=~np.isclose(av,bv,atol=1e-8,rtol=1e-8)
  for ph in ['train','validation','holdout','later']:
   n=int(badcells[phases.eq(ph)].sum())
   if n:change[ph][name]=n
 del groups,replacements,repl,oldmatch
 save('input_changes.json',dict(counts=counts,changed_cells_by_period=change,empty_history_margin='Match frozen online behavior: rider_avg_margin=0 when rider_race_count=0',replacement_columns=replace_cols,source='entries for current race, races for metadata, strictly earlier dates for rider history; no current result fallback'))
 # Independently call the unmodified online builder with historical class from entries.
 parity=[];bad=0
 for ph,n in [('train',80),('validation',80),('holdout',240)]:
  ids=sorted(set(clean.loc[clean.race_date.map(phase)==ph,'race_id']));ix=sorted(set(int(x) for x in np.linspace(0,len(ids)-1,min(n,len(ids)))))
  for j in ix:
   rid=ids[j];g=clean[clean.race_id==rid];day=str(g.iloc[0].race_date);con.execute('SAVEPOINT parity')
   try:
    for _,r in g.iterrows():con.execute('UPDATE riders SET class=? WHERE rider_id=?',(r['class'],str(r.rider_id)))
    online=builder.build_race_features(str(rid),day,Guard(con,day));a=g.set_index('rider_id');b=online.set_index('rider_id').loc[a.index]
    aa=a[features].apply(pd.to_numeric,errors='coerce').fillna(0);bb=b[features].apply(pd.to_numeric,errors='coerce').fillna(0);diff=[f for f in features if not np.allclose(aa[f],bb[f],atol=1e-8,rtol=1e-8)]
    sa=oldmodel.predict(aa).to_numpy();sb=oldmodel.predict(bb).to_numpy();oa=np.lexsort((a.bike_number.to_numpy(),-sa));ob=np.lexsort((a.bike_number.to_numpy(),-sb));score_match=np.allclose(sa,sb,atol=1e-8,rtol=1e-8)
    # Current result permutation is explicitly irrelevant to online queries: Guard forbids reading it.
    parity.append(dict(race_id=rid,phase=ph,changed_features=diff,identical=not diff,score_match=bool(score_match),rank_match=bool(np.array_equal(oa,ob))))
    bad+=bool(diff) or not score_match or not np.array_equal(oa,ob)
    if j%10==0:
     con.execute("UPDATE race_results SET finish_position=NULL,line_group='current_result_hidden',line_role='hidden',class='L1' WHERE race_id=?",(str(rid),))
     hidden=builder.build_race_features(str(rid),day,Guard(con,day)).set_index('rider_id').loc[a.index]
     invariant=bool(np.allclose(bb,hidden[features].apply(pd.to_numeric,errors='coerce').fillna(0),atol=1e-8,rtol=1e-8))
     parity[-1]['current_outcome_hidden_invariant']=invariant;bad+=not invariant
   finally:con.execute('ROLLBACK TO parity');con.execute('RELEASE parity')
  print('PARITY_PHASE',ph,'bad',bad,flush=True)
 save('parity.json',parity)
 assert bad==0,f'Online parity failed in {bad} races; refuse to claim corrected ROI'
 train=clean[clean.race_date<TRAIN_END];val=clean[(clean.race_date>=TRAIN_END)&(clean.race_date<VALID_END)];test=clean[(clean.race_date>=VALID_END)&(clean.race_date<TEST_END)]
 train,xt,yt,gt=split(train,features);val,xv,yv,gv=split(val,features);test,_,_,_=split(test,features)
 fixed=predict_ledger(test,oldmodel,features,'fixed_model_entry_inputs')
 oldscope=old[old.race_id.isin(set(test.race_id))];before=predict_ledger(oldscope,oldmodel,features,'old_batch_matched_scope')
 save('fixed_model_summary.json',dict(model_sha256=SHA,parity_compared=len(parity),parity_failures=bad,counts=counts,changes=change,original_batch=before,entry_replay=fixed,features=features))
 print('FIXED_MODEL_REPLAY',json.dumps(fixed['combined']),flush=True)
 # Retain intermediate report before candidate training starts.
 import subprocess
 subprocess.run(['git','add','-f',str(OUT)],check=True);subprocess.run(['git','commit','-m','Record entry-only fixed-model replay and parity [skip ci]'],check=True);subprocess.run(['git','push','origin','HEAD:research/entry-only-validation-20261026'],check=True)
 candidate=LGBMRanker();candidate.train(xt,yt,gt,xv,yv,gv);candidate.save(str(OUT/'entry_only_research_model.pkl'))
 result=predict_ledger(test,candidate,features,'clean_retrained_research')
 save('final_summary.json',dict(frozen_model_sha256=SHA,candidate_sha256=hashlib.sha256((OUT/'entry_only_research_model.pkl').read_bytes()).hexdigest(),split_races=dict(train=len(gt),validation=len(gv),holdout=test.race_id.nunique()),parity_compared=len(parity),parity_failures=bad,input_changes=dict(counts=counts,changed_cells=change),fixed_model_original_batch=before,fixed_model_entry_replay=fixed,clean_retrained_research=result,feature_importance_original=oldmodel.feature_importance().to_dict('records'),feature_importance_candidate=candidate.feature_importance().to_dict('records'),limitations=['Retrospectively collected archive entries lack proof of pre-race capture timestamps.','Historical rider master class is aligned using current-race entry class, not finish results.','44-feature batch equivalence verified against frozen online builder on 400 deterministic samples, not every race.','Purchase thresholds are previously selected and not new untouched holdout choices.','Final-odds filter must be computed separately; do not call it pre-purchase odds replay.','No production source, model, forecasts, or pages modified.']))
 print('CLEAN_RETRAINED_RESEARCH',json.dumps(result['combined']),flush=True)
 assert hashlib.sha256(Path(MODEL).read_bytes()).hexdigest()==SHA

if __name__=='__main__':main()
