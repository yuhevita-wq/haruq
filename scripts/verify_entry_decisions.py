"""Independent online prediction and ticket parity on deterministic holdout samples."""
import csv,json,itertools,sqlite3,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from config import DB_PATH
from features.builder import FeatureBuilder
from models.lgbm_ranker import LGBMRanker
from scripts.entry_only_redo import Guard,SHA,MODEL
P=Path('entry_only_redo');con=sqlite3.connect(DB_PATH);con.row_factory=sqlite3.Row;b=FeatureBuilder();out=[]
assert hashlib.sha256(Path(MODEL).read_bytes()).hexdigest()==SHA
for label,path in [('fixed_model_entry_inputs',MODEL),('clean_retrained_research',str(P/'entry_only_research_model.pkl'))]:
 expected=SHA if label=='fixed_model_entry_inputs' else json.load(open(P/'final_summary.json'))['candidate_sha256']
 assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==expected
 model=LGBMRanker();model.load(path);rows=list(csv.DictReader(open(P/(label+'_predictions.csv'))));ix=sorted(set(int(x) for x in np.linspace(0,len(rows)-1,min(400,len(rows)))))
 for j in ix:
  r=rows[j];rid=r['race_id'];day=r['date'];es=con.execute('SELECT rider_id,class FROM entries WHERE race_id=?',(rid,)).fetchall();assert es
  con.execute('SAVEPOINT verify')
  try:
   for e in es:con.execute('UPDATE riders SET class=? WHERE rider_id=?',(e['class'],e['rider_id']))
   df=b.build_race_features(rid,day,Guard(con,day));ss=model.predict(df[model.feature_names].apply(pd.to_numeric,errors='coerce').fillna(0)).to_numpy();bike=df.entry_bike_number.astype(int).to_numpy();order=np.lexsort((bike,-ss));bs=bike[order].tolist();gap=float(ss[order[0]]-ss[order[1]])
   ex=';'.join(f'{bs[0]}>{x}' for x in bs[1:5]) if gap>=1 else '';tri=';'.join(f'{bs[0]}>{x}>{y}' for x,y in itertools.permutations(bs[1:4],2)) if gap>=2 else ''
   rank='>'.join(map(str,bs));ok=rank==r['ranked_bikes'] and abs(gap-float(r['gap']))<=1e-8 and ex==r['exacta_tickets'] and tri==r['trifecta_tickets']
   out.append(dict(model=label,race_id=rid,rank_match=rank==r['ranked_bikes'],gap_abs_difference=abs(gap-float(r['gap'])),exacta_tickets_match=ex==r['exacta_tickets'],trifecta_tickets_match=tri==r['trifecta_tickets'],all_match=ok))
  finally:con.execute('ROLLBACK TO verify');con.execute('RELEASE verify')
 print('DECISION_PARITY',label,sum(x['all_match'] for x in out if x['model']==label),len(ix),flush=True)
(P/'decision_parity.json').write_text(json.dumps(dict(compared=len(out),failures=sum(not x['all_match'] for x in out),records=out),ensure_ascii=False,indent=2))
assert all(x['all_match'] for x in out),'Online purchase/ticket parity failed'
