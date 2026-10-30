"""Aggregate all 12 monthly jobs; never promote partial results to full-year ROI."""
from collections import Counter,defaultdict
import gzip,json
from pathlib import Path

root=Path('annual_results');root.mkdir(exist_ok=True)
reports=sorted(Path('monthly_results').glob('**/summary.json'))
months=[json.loads(p.read_text()) for p in reports]
assert len(months)==12 and {x['month'] for x in months}=={f'2023-{i:02d}' for i in range(1,13)},'All 12 monthly summaries required'
status=Counter();totals=defaultdict(Counter)
for m in months:
    assert m['all_records_accounted']
    status.update(m['statuses'])
    for k,v in m['totals'].items():totals[k].update(v)
for d in totals.values():
    d['net_yen']=d['returned_yen']-d['investment_yen']
    d['roi_percent']=100*d['returned_yen']/d['investment_yen'] if d['investment_yen'] else None
summary={'period':['2023-01-01','2023-12-31'],'months':months,
    'universe':sum(m['universe'] for m in months),'recorded':sum(m['recorded'] for m in months),
    'statuses':dict(status),'data_complete':all(m['data_complete'] for m in months),
    'totals':{k:dict(v) for k,v in totals.items()},'model_test_status':'IN_SAMPLE_RETROSPECTIVE',
    'manual_H1_status':'Hypothetical 100-yen purchases of research candidates, not production purchases',
    'coverage':'All archive DB races union independent odds calendar; unresolved records retained, never zero-loss imputed',
    'price_selection':'Default H1 selection without prices; no final-odds purchase-time claim'}
(root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
ids=set()
with gzip.open(root/'all_races.jsonl.gz','wt') as out:
    for p in sorted(Path('monthly_results').glob('**/races.jsonl.gz')):
        with gzip.open(p,'rt') as f:
            for line in f:
                obj=json.loads(line);rid=obj['race_id']
                assert rid not in ids,'Duplicate race across monthly shards';ids.add(rid);out.write(line)
assert len(ids)==summary['recorded']==summary['universe']
print('YEAR_AGGREGATED',len(ids),'records; results saved')
