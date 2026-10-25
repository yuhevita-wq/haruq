import csv,json,itertools,sqlite3,hashlib,os,subprocess
from pathlib import Path
import pandas as pd
import numpy as np
from config import DB_PATH
from features.builder import FeatureBuilder
from models.lgbm_ranker import LGBMRanker
from scripts.entry_only_redo import Guard
from scripts.reproduce_haruqube_20260321 import verify_sources
verify_sources();P=Path('recovery_186_v1');S=json.load(open(P/'summary.json'));con=sqlite3.connect(DB_PATH);con.row_factory=sqlite3.Row;builder=FeatureBuilder();out=[];loaded={}
for name in ['baseline']+list(S['models']):
 file=Path('entry_only_redo/entry_only_research_model.pkl') if name=='baseline' else P/(name+'.pkl');expected=S['baseline_model_sha256'] if name=='baseline' else S['models'][name]['model_sha256'];assert hashlib.sha256(file.read_bytes()).hexdigest()==expected
 m=LGBMRanker();m.load(str(file));loaded[name]=m;rows=list(csv.DictReader(open(P/(name+'_predictions.csv'))));ix=sorted(set(int(i) for i in np.linspace(0,len(rows)-1,min(400,len(rows)))))
 for j in ix:
  r=rows[j];rid=r['race_id'];day=r['date'];es=con.execute('SELECT rider_id,class FROM entries WHERE race_id=?',(rid,)).fetchall();assert es;con.execute('SAVEPOINT verify')
  try:
   for e in es:con.execute('UPDATE riders SET class=? WHERE rider_id=?',(e['class'],e['rider_id']))
   f=builder.build_race_features(rid,day,Guard(con,day));sc=m.predict(f[m.feature_names].apply(pd.to_numeric,errors='coerce').fillna(0)).to_numpy();bike=f.entry_bike_number.astype(int).to_numpy();order=np.lexsort((bike,-sc));bs=bike[order].tolist();gap=float(sc[order[0]]-sc[order[1]]);ex=';'.join(f'{bs[0]}>{b}' for b in bs[1:5]) if gap>=1 else '';tri=';'.join(f'{bs[0]}>{b}>{c}' for b,c in itertools.permutations(bs[1:4],2)) if gap>=2 else ''
   ok='>'.join(map(str,bs))==r['ranked_bikes'] and abs(gap-float(r['gap']))<=1e-8 and ex==r['exacta_tickets'] and tri==r['trifecta_tickets'];out.append(dict(model=name,race_id=rid,all_match=ok,gap_difference=abs(gap-float(r['gap']))))
  finally:con.execute('ROLLBACK TO verify');con.execute('RELEASE verify')
 print('ONLINE_DECISION_PARITY',name,len(ix),'failures',sum(not x['all_match'] for x in out if x['model']==name),flush=True)
(P/'independent_decision_parity.json').write_text(json.dumps(dict(compared=len(out),failures=sum(not x['all_match'] for x in out),records=out),ensure_ascii=False,indent=2));assert all(x['all_match'] for x in out)

# Predeclared additional period, never used to select candidates in this experiment.
import scripts.recovery_186_v1 as recovery
import scripts.entry_only_redo as prior
prior.OUT=P
work=Path('work');work.mkdir(exist_ok=True);tag='entry-only-features-research-v1-20261026'
for asset in ['entry_only_features.pkl.gz.gpg','entry_only_features_manifest.json']:
 subprocess.run(['gh','release','download',tag,'--repo',os.environ['GITHUB_REPOSITORY'],'--pattern',asset,'--dir',str(work),'--clobber'],check=True,capture_output=True)
manifest=json.load(open(work/'entry_only_features_manifest.json'));enc=work/'entry_only_features.pkl.gz.gpg';plain=work/'entry_only_features.pkl.gz'
assert hashlib.sha256(enc.read_bytes()).hexdigest()==manifest['ciphertext_sha256']
subprocess.run(['gpg','--batch','--yes','--pinentry-mode','loopback','--passphrase-fd','0','--output',str(plain),'--decrypt',str(enc)],input=os.environ['COLLECTOR_PASSPHRASE'].rstrip('\r\n').encode(),check=True,capture_output=True)
assert hashlib.sha256(plain.read_bytes()).hexdigest()==manifest['plaintext_sha256']
frame=pd.read_pickle(plain,compression='gzip');plain.unlink();extra=frame[(frame.race_date>='2026-10-01')&(frame.race_date<'2026-10-23')].copy();assert extra.race_id.nunique()>=100
ids=sorted(set(extra.race_id));checks=[];features=S['feature_names']
for i in sorted(set(map(int,np.linspace(0,len(ids)-1,min(80,len(ids)))))):
 rid=ids[i];g=extra[extra.race_id==rid];day=str(g.iloc[0].race_date);con.execute('SAVEPOINT extra')
 try:
  for _,r in g.iterrows():con.execute('UPDATE riders SET class=? WHERE rider_id=?',(r['class'],str(r.rider_id)))
  a=g.set_index('rider_id')[features];b=builder.build_race_features(rid,day,Guard(con,day)).set_index('rider_id').loc[a.index,features].apply(pd.to_numeric,errors='coerce').fillna(0)
  checks.append(dict(race_id=rid,all_match=bool(np.allclose(a,b,atol=1e-8,rtol=1e-8))))
 finally:con.execute('ROLLBACK TO extra');con.execute('RELEASE extra')
assert all(x['all_match'] for x in checks)
result={};quality={}
for name in dict.fromkeys(['baseline',S['selected_on_validation']]):
 result[name]=prior.predict_ledger(extra,loaded[name],features,name+'_october_additional');quality[name]=recovery.metrics(extra,loaded[name],features)
(P/'october_additional_summary.json').write_text(json.dumps(dict(period='2026-10-01 through 2026-10-22',races=extra.race_id.nunique(),selected_on_prior_validation=S['selected_on_validation'],odds_filter_applied=False,reason='Full selected-ticket final odds unavailable in this period; no substitution.',selection_uses_this_period=False,feature_parity=checks,holdout=result,prediction_quality=quality),ensure_ascii=False,indent=2))
print('OCTOBER_ADDITIONAL',json.dumps({n:r['combined'] for n,r in result.items()}),flush=True)
