"""Predeclared first recovery experiment. Production model and purchase policy untouched."""
import collections,csv,hashlib,json,sqlite3,subprocess,os
from pathlib import Path
import numpy as np
import pandas as pd
from config import DB_PATH,CLASS_MAP,LGBM_PARAMS
from features.builder import FeatureBuilder
from models.lgbm_ranker import LGBMRanker
from scripts.reproduce_haruqube_fresh import dataset,split,TRAIN_END,VALID_END,TEST_END
from scripts.reproduce_haruqube_20260321 import verify_sources
import scripts.entry_only_redo as prior

OUT=Path('recovery_186_v1');OUT.mkdir(exist_ok=True);prior.OUT=OUT
BRANCH='research/recovery-186-v1-20261026'
SPECS=[dict(name='eligible_train_ndcg3',eligible_train=True,head_focus=False),dict(name='all_train_head_focus',eligible_train=False,head_focus=True),dict(name='eligible_train_head_focus',eligible_train=True,head_focus=True)]
def save(name,obj):
 (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=lambda x:x.item() if hasattr(x,'item') else str(x)))
def publish(message):
 subprocess.run(['git','add','-f',str(OUT)],check=True);subprocess.run(['git','commit','-m',message+' [skip ci]'],check=True);subprocess.run(['git','push','origin','HEAD:'+BRANCH],check=True)
def eligible(df):
 cls=df['class'].fillna('').astype(str).str.upper();girl=cls.str.startswith(('L','Ｌ'));unknown=cls.isin(['','0','0.0','NONE','NAN']);bad=girl.groupby(df.race_id).transform('any')|unknown.groupby(df.race_id).transform('all');return df[~bad].copy()

def rebuild(old,builder,con,features):
 """Bulk metadata merge; only the original line reader is per race, preserving exact query order."""
 entries=pd.read_sql_query('SELECT * FROM entries',con);ids=set(old.race_id);entries=entries[entries.race_id.isin(ids)].copy()
 assert not entries.duplicated(['race_id','rider_id']).any()
 keys=old[['race_id','rider_id']].merge(entries[['race_id','rider_id']],how='left',indicator=True,validate='one_to_one')
 expected=old.groupby('race_id').size();actual=entries.groupby('race_id').size();incomplete=set(expected.index[expected.ne(actual.reindex(expected.index))])|set(keys.loc[keys['_merge']!='both','race_id'])
 invalid=set(entries.loc[entries.bike_number.isna(),'race_id']);nunique=entries.groupby('race_id').bike_number.nunique();invalid|=set(actual.index[actual.ne(nunique)])
 keep=ids-incomplete-invalid;old=old[old.race_id.isin(keep)].copy();entries=entries[entries.race_id.isin(keep)]
 updates=entries[['race_id','rider_id','class','line_group','line_role','bike_number','frame_number']].copy()
 for dest,src,default in [('entry_frame_number','frame_number',1),('entry_bike_number','bike_number',1),('entry_gear_ratio','gear_ratio',3.93),('entry_competition_score','avg_competition_score',0),('entry_win_rate','win_rate',0),('entry_place_rate','place_rate',0)]:
  updates[dest]=entries[src].fillna(default)
  if dest in ['entry_frame_number','entry_bike_number','entry_gear_ratio']:updates[dest]=updates[dest].replace(0,default)
 line=[]
 for j,rid in enumerate(sorted(keep)):
  fs=builder.line_builder._build_all(con,str(rid))
  # Completeness precheck above forbids the frozen reader's result fallback.
  line.extend(dict(race_id=rid,rider_id=k,**v) for k,v in fs.items())
  if j%10000==0:print('ENTRY_LINES',j,len(keep),flush=True)
 lf=pd.DataFrame(line);assert not lf.duplicated(['race_id','rider_id']).any()
 replace=set(updates)|set(lf);replace-=set(['race_id','rider_id'])
 clean=old.drop(columns=[c for c in replace if c in old]).merge(updates,on=['race_id','rider_id'],validate='one_to_one').merge(lf,on=['race_id','rider_id'],validate='one_to_one')
 assert len(clean)==len(old)
 clean['rider_class_num']=clean['class'].map(CLASS_MAP).fillna(6).astype(float);clean['class_rank_in_race']=clean.groupby('race_id').rider_class_num.rank(method='min');clean['rider_class_x_jiku']=clean.rider_class_num*clean.line_is_jiku;clean['form_trend_x_line_strength']=clean.rider_form_trend*clean.line_strength_score;clean.loc[clean.rider_race_count==0,'rider_avg_margin']=0.
 clean[features]=clean[features].apply(pd.to_numeric,errors='coerce').fillna(0)
 save('input_coverage.json',dict(races_before=len(ids),races_after=len(keep),incomplete_entries=len(incomplete),invalid_entry_bikes=len(invalid),feature_source='Current metadata and lines from entries; strictly prior dates for rider statistics. Empty-history margin matches online0. No result fallback.'))
 return clean

def parity(clean,builder,con,features):
 rows=[]
 for start,end,n in [('2023-01-01',TRAIN_END,80),(TRAIN_END,VALID_END,80),(VALID_END,TEST_END,240)]:
  ids=sorted(set(clean.loc[(clean.race_date>=start)&(clean.race_date<end),'race_id']))
  for ix in sorted(set(map(int,np.linspace(0,len(ids)-1,n)))):
   rid=ids[ix];g=clean[clean.race_id==rid];day=str(g.iloc[0].race_date);con.execute('SAVEPOINT parity')
   try:
    for _,r in g.iterrows():con.execute('UPDATE riders SET class=? WHERE rider_id=?',(r['class'],str(r.rider_id)))
    a=g.set_index('rider_id')[features];online=builder.build_race_features(str(rid),day,prior.Guard(con,day)).set_index('rider_id').loc[a.index,features].apply(pd.to_numeric,errors='coerce').fillna(0)
    diff=[f for f in features if not np.allclose(a[f],online[f],atol=1e-8,rtol=1e-8)];rows.append(dict(race_id=rid,changed_features=diff,all_match=not diff))
   finally:con.execute('ROLLBACK TO parity');con.execute('RELEASE parity')
 save('input_parity.json',rows);assert all(x['all_match'] for x in rows),'Current feature engine differs from frozen online builder'
 print('INPUT_PARITY',len(rows),'failures',sum(not x['all_match'] for x in rows),flush=True)

def metrics(frame,model,features):
 f=eligible(frame);f['s']=model.predict(f[features]).values;rows=[]
 for rid,g in f.groupby('race_id',sort=False):
  rank=g.sort_values(['s','bike_number'],ascending=[False,True],kind='stable');bs=rank.bike_number.astype(int).tolist();actual=g.sort_values('finish_position').bike_number.astype(int).tolist();pos=int(rank.iloc[0].finish_position);n=len(g);rel=n-pos+1
  rows.append(dict(top1=int(bs[0]==actual[0]),exacta4=int(bs[0]==actual[0] and actual[1] in bs[1:5]),trifecta6=int(bs[0]==actual[0] and actual[1] in bs[1:4] and actual[2] in bs[1:4]),ndcg1=(2**rel-1)/(2**n-1),gap=float(rank.iloc[0].s-rank.iloc[1].s)))
 return dict(races=len(rows),top1_hits=sum(x['top1'] for x in rows),top1_rate=sum(x['top1'] for x in rows)/len(rows),exacta4_hit_rate=sum(x['exacta4'] for x in rows)/len(rows),trifecta6_hit_rate=sum(x['trifecta6'] for x in rows)/len(rows),ndcg1=float(np.mean([x['ndcg1'] for x in rows])),high_races=sum(x['gap']>=1 for x in rows),s3_high_races=sum(x['gap']>=2 for x in rows))

def main():
 verify_sources();base_meta=json.load(open('entry_only_redo/final_summary.json'));basefile=Path('entry_only_redo/entry_only_research_model.pkl');assert hashlib.sha256(basefile.read_bytes()).hexdigest()==base_meta['candidate_sha256']
 baseline=LGBMRanker();baseline.load(str(basefile));builder=FeatureBuilder();old,features,_=dataset();con=sqlite3.connect(DB_PATH);con.row_factory=sqlite3.Row
 pay=pd.read_sql_query('SELECT race_id,sanrentan_combo,sanrentan_payout FROM race_payouts',con);old=old.merge(pay,on='race_id',validate='many_to_one',how='left')
 clean=rebuild(old,builder,con,features);del old;parity(clean,builder,con,features)
 train=clean[clean.race_date<TRAIN_END];val=clean[(clean.race_date>=TRAIN_END)&(clean.race_date<VALID_END)];test=clean[(clean.race_date>=VALID_END)&(clean.race_date<TEST_END)]
 train,_,_,_=split(train,features);val,_,_,_=split(val,features);test,_,_,_=split(test,features)
 prior.predict_ledger(test,baseline,features,'baseline_reproduction')
 previous={r['race_id']:r for r in csv.DictReader(open('entry_only_redo/clean_retrained_research_predictions.csv'))};now=list(csv.DictReader(open(OUT/'baseline_reproduction_predictions.csv')));assert len(now)==len(previous)
 for r in now:
  o=previous[r['race_id']];assert r['ranked_bikes']==o['ranked_bikes'] and abs(float(r['gap'])-float(o['gap']))<=1e-8 and r['exacta_tickets']==o['exacta_tickets'] and r['trifecta_tickets']==o['trifecta_tickets'],r['race_id']
 print('BASELINE_REPRODUCED',len(now),flush=True)
 # Retain only encrypted feature checkpoints for future research; never commit plaintext inputs.
 work=Path('work');work.mkdir(exist_ok=True);plain=work/'entry_only_features.pkl.gz';encrypted=work/'entry_only_features.pkl.gz.gpg';manifest=work/'entry_only_features_manifest.json'
 clean.to_pickle(plain,compression='gzip');secret=os.environ['COLLECTOR_PASSPHRASE'].rstrip('\r\n').encode()
 subprocess.run(['gpg','--batch','--yes','--pinentry-mode','loopback','--passphrase-fd','0','--symmetric','--cipher-algo','AES256','--output',str(encrypted),str(plain)],input=secret,check=True,capture_output=True)
 manifest.write_text(json.dumps(dict(schema=1,plaintext_sha256=hashlib.sha256(plain.read_bytes()).hexdigest(),ciphertext_sha256=hashlib.sha256(encrypted.read_bytes()).hexdigest(),source_commit=os.environ['GITHUB_SHA'],features=features,rows=len(clean),races=clean.race_id.nunique(),parity_races=400,baseline_prediction_parity=len(now)),indent=2))
 plain.unlink();tag='entry-only-features-research-v1-20261026'
 exists=subprocess.run(['gh','release','view',tag,'--repo',os.environ['GITHUB_REPOSITORY']],capture_output=True).returncode==0
 if not exists:
  subprocess.run(['gh','release','create',tag,'--repo',os.environ['GITHUB_REPOSITORY'],'--draft','--target',os.environ['GITHUB_SHA'],'--title',tag,'--notes','Encrypted entry-only feature checkpoint. No production model changes.'],check=True,capture_output=True)
  subprocess.run(['gh','release','upload',tag,str(encrypted),str(manifest),'--repo',os.environ['GITHUB_REPOSITORY']],check=True,capture_output=True)
 print('ENCRYPTED_FEATURE_CHECKPOINT_RETAINED',flush=True)

 models={'baseline':baseline};valid={'baseline':metrics(val,baseline,features)};details={}
 for spec in SPECS:
  name=spec['name'];tr=eligible(train) if spec['eligible_train'] else train;va=eligible(val);_,xt,yt,gt=split(tr,features);_,xv,yv,gv=split(va,features);params=LGBM_PARAMS.copy()
  if spec['head_focus']:params['ndcg_eval_at']=[1];params['lambdarank_truncation_level']=4
  m=LGBMRanker(params=params);m.train(xt,yt,gt,xv,yv,gv);file=OUT/(name+'.pkl');m.save(str(file));models[name]=m;valid[name]=metrics(val,m,features);details[name]=dict(spec,params=params,train_races=len(gt),early_stopping_validation_races=len(gv),model_sha256=hashlib.sha256(file.read_bytes()).hexdigest());print('VALIDATION_MODEL',name,json.dumps(valid[name]),flush=True)
 # Predeclared ordering: top1 hits, then exacta4 hit rate, then NDCG1; final holdout ROI is not a selection input.
 winner=max(models,key=lambda n:(valid[n]['top1_hits'],valid[n]['exacta4_hit_rate'],valid[n]['ndcg1']))
 save('selection_frozen_before_holdout.json',dict(selected=winner,selection_rule='2025H1 eligible validation top1 hits, then exacta4 hit rate, then NDCG1. No holdout profit or odds used.',validation=valid,models=details,production_changed=False,target_roi_pct=186.3,policy='HIGH gap>=1 exacta4; S3-HIGH gap>=2 trifecta6; 100yen each; requested <=4 final odds filter applied separately without tuning'))
 publish('Freeze recovery-v1 selection before candidate holdout evaluation')
 result={};quality={}
 for name,m in models.items():
  result[name]=prior.predict_ledger(test,m,features,name);quality[name]=metrics(test,m,features);print('HOLDOUT_MODEL',name,json.dumps(result[name]['combined']),flush=True)
 save('summary.json',dict(target_roi_pct=186.3,target_achieved=False,target_status='Final-odds filtering and external online parity pending; do not claim success from unfiltered ROI.',selected_on_validation=winner,validation=valid,holdout=result,holdout_prediction_quality=quality,split_races=dict(train=train.race_id.nunique(),validation=val.race_id.nunique(),holdout=test.race_id.nunique()),models=details,baseline_model_sha256=base_meta['candidate_sha256'],baseline_full_prediction_reproduction=len(now),input_feature_parity=400,feature_names=features,production_changed=False,limitations=['This previously viewed archive is not a brand-new untouched holdout; candidate choice in this experiment does not read its returns.','Score gap thresholds are held fixed across objectives; score-scale changes can alter participation.','Final-odds <=4 filter is a retrospective reference, not a pre-purchase odds replay.','No model or policy promoted to production.']))
 print('RECOVERY_V1_COMPLETE',winner,flush=True)
if __name__=='__main__':main()
