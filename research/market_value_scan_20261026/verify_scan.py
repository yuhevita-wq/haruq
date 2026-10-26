import argparse,collections,csv,hashlib,json,math
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();P=args.output
rows=list(csv.DictReader((P/'all_pattern_price_temporal_comparison.csv').open()));s=json.load(open(P/'summary.json'));diag=list(csv.DictReader((P/'early_positive_persistence_diagnostic.csv').open()))
checks=0
for phase in ['early','later']:
    for market in ['exacta','trifecta']:
        for scope in ['early_positive_all','early_positive_HIGH_MEDplus_MED']:
            rs=[r for r in rows if r['band_scheme']=='exacta_band' and r['market']==market and r['early_positive']=='True' and (scope=='early_positive_all' or r['band']!='LOW')]
            d=next(r for r in diag if r['diagnostic']==scope and r['market']==market and r['period']==('early_2025H2' if phase=='early' else 'later_2026H1'))
            assert int(d['opportunities'])==sum(int(r[phase+'_opportunities']) for r in rs)
            assert int(d['returned_yen'])==sum(round(float(r[phase+'_return_units'])*100) for r in rs)
            assert int(d['hits'])==sum(int(r[phase+'_hits']) for r in rs);checks+=1
        primary=[r for r in rows if r['band_scheme']=='exacta_band' and r['market']==market]
        period='early_2025H2' if phase=='early' else 'later_2026H1'
        assert sum(int(r[phase+'_opportunities']) for r in primary)==s['candidate_quote_counts'][str((period,market))]
        if market=='trifecta':
            native=[r for r in rows if r['band_scheme']=='trifecta_band']
            for field in ['opportunities','hits']:
                assert sum(int(r[phase+'_'+field]) for r in primary)==sum(int(r[phase+'_'+field]) for r in native)
            assert sum(round(float(r[phase+'_return_units'])*100) for r in primary)==sum(round(float(r[phase+'_return_units'])*100) for r in native)
        for r in primary:
            N=int(r[phase+'_opportunities']);yen=round(float(r[phase+'_return_units'])*100)
            assert (r[phase+'_positive']=='True')==(N>0 and yen>N*100)
            if N:assert abs(float(r[phase+'_roi_pct'])-yen/N)<1e-9
            else:assert r[phase+'_roi_pct']==''
for d in diag:
    N=int(d['opportunities']);R=int(d['returned_yen']);assert int(d['investment_yen'])==N*100 and int(d['profit_yen'])==R-N*100
control=[r for r in diag if r['diagnostic']=='unchanged_control' and r['market']=='combined']
assert sum(int(r['investment_yen']) for r in control)==318000
assert sum(int(r['returned_yen']) for r in control)==266350
pool=list(csv.DictReader((P/'pooled_price_band_returns.csv').open()))
for r in pool:
    if int(r['hits'])==0 and int(r['opportunities'])>0:assert r['day_bootstrap95_lower']==r['day_bootstrap95_upper']==''
for name,h in s['output_sha256'].items():assert hashlib.sha256((P/name).read_bytes()).hexdigest()==h
un=json.load(open(P/'unordered_summary.json'))
result=dict(status='passed',all_ordered_cells=len(rows),independent_export_to_full_book_persistence_reconciliations=checks,
            unordered_checks=un['crosscheck'],unchanged_control_investment=318000,unchanged_control_return=266350,
            monetary_positive_boundary_checked=True,primary_native_trifecta_totals_match=True,
            unobserved_future_not_inferred_from_zero_hits=True,production_changed=False)
(P/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result),flush=True)
