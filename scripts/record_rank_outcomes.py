"""Record outcomes against previously frozen predictions; no training or policy changes."""
import collections, csv, hashlib, json, math, re, sqlite3
from pathlib import Path

BASE = Path('recovery_186_v1')
OUT = Path('rank_outcomes_20261026')
OUT.mkdir(exist_ok=True)
MODEL = 'eligible_train_ndcg3'
SOURCE_COMMIT = '8f53e20611929734b0e59d45f1c7d7f9742c1a71'
META = json.loads((BASE / 'summary.json').read_text())
assert META['selected_on_validation'] == MODEL
MODEL_SHA = META['models'][MODEL]['model_sha256']

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def dumpcsv(name, rows, fields=None):
    fields = fields or list(rows[0])
    with (OUT / name).open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

def category(gap, strategies, fallback):
    return next((label for threshold, label in strategies if gap >= threshold), fallback)

EX_BANDS = [(1.0, 'HIGH'), (0.8, 'MED+'), (0.5, 'MED')]
TRI_BANDS = [(2.0, 'S3-HIGH'), (1.5, 'S3-MED+'), (1.0, 'S3-MED')]
con = sqlite3.connect('file:db/keirin.db?mode=ro', uri=True)
con.row_factory = sqlite3.Row
results = collections.defaultdict(list)
for x in con.execute('SELECT race_id,rider_id,bike_number,finish_position FROM race_results'):
    results[str(x['race_id'])].append(dict(x))
entries = collections.defaultdict(list)
for x in con.execute('SELECT race_id,rider_id,bike_number FROM entries'):
    entries[str(x['race_id'])].append(dict(x))
race_meta = {str(x['race_id']):dict(x) for x in con.execute('SELECT race_id,date,grade,rider_count FROM races')}
payouts = {}
for x in con.execute('SELECT race_id,nisyatan_combo,nisyatan_payout,sanrentan_combo,sanrentan_payout FROM race_payouts'):
    assert str(x['race_id']) not in payouts
    payouts[str(x['race_id'])] = dict(x)
con.close()

records, issues, inputs = [], [], []
seen = set()
for filename, phase in [(MODEL+'_predictions.csv', 'main_2025H2_2026Q3'), (MODEL+'_october_additional_predictions.csv', 'additional_2026Oct01_22')]:
    path = BASE / filename
    rows = list(csv.DictReader(path.open()))
    inputs.append(dict(path=str(path), sha256=sha(path), rows=len(rows)))
    for pred in rows:
        rid = pred['race_id']
        assert rid not in seen, ('duplicate prediction', rid)
        seen.add(rid)
        bikes = list(map(int, pred['ranked_bikes'].split('>')))
        gap = float(pred['gap'])
        assert math.isfinite(gap) and len(bikes) == len(set(bikes)) and len(bikes) >= 3
        inverse = {bike: i+1 for i, bike in enumerate(bikes)}
        rr, ee, meta = results[rid], entries[rid], race_meta.get(rid, {})
        problems = []
        if str(meta.get('date')) != pred['date']: problems.append('race_date_mismatch')
        if str(meta.get('grade')) != pred['grade']: problems.append('race_grade_mismatch')
        if len(rr) != len(bikes) or meta.get('rider_count') != len(bikes): problems.append('result_count_mismatch')
        if len(ee) != len(bikes): problems.append('entry_count_mismatch')
        try:
            rr = sorted(rr, key=lambda x: int(x['finish_position']))
            positions = [int(x['finish_position']) for x in rr]
            actual = [int(x['bike_number']) for x in rr]
            if len(set(positions)) != len(positions) or any(p < 1 for p in positions): problems.append('ambiguous_finish_positions')
            if positions[:3] != [1, 2, 3]: problems.append('missing_unambiguous_top3')
            if len(set(actual)) != len(actual) or set(actual) != set(bikes): problems.append('prediction_result_bike_set_mismatch')
            eb = {str(x['rider_id']):int(x['bike_number']) for x in ee}
            if len(eb) != len(ee) or set(eb) != {str(x['rider_id']) for x in rr}: problems.append('entry_result_rider_set_mismatch')
            elif any(eb[str(x['rider_id'])] != int(x['bike_number']) for x in rr): problems.append('entry_result_bike_mismatch')
        except (TypeError, ValueError, KeyError):
            problems.append('invalid_result_numbers')
        row = dict(model=MODEL, model_sha256=MODEL_SHA, prediction_source_commit=SOURCE_COMMIT,
            phase=phase, race_id=rid, date=pred['date'], grade=pred['grade'], rider_count=len(bikes),
            score_gap=pred['gap'], exacta_band=category(gap, EX_BANDS, 'LOW'),
            trifecta_band=category(gap, TRI_BANDS, 'S3-LOW'),
            ranked_bikes=pred['ranked_bikes'], outcome_status='quarantined' if problems else 'ok',
            issue_codes=';'.join(problems), actual_finish_positions='', actual_bikes='', actual_pred_ranks='',
            actual_first_bike='', actual_second_bike='', actual_third_bike='',
            actual_first_pred_rank='', actual_second_pred_rank='', actual_third_pred_rank='',
            exacta_rank_pattern='', trifecta_rank_pattern='',
            exacta_payout_yen_per_100='', exacta_payout_verified=False,
            trifecta_payout_yen_per_100='', trifecta_payout_verified=False)
        if problems:
            issues.append(dict(race_id=rid, issues=problems))
        else:
            ranks = [inverse[b] for b in actual]
            row.update(actual_finish_positions='>'.join(map(str, positions)), actual_bikes='>'.join(map(str, actual)),
                actual_pred_ranks='>'.join(map(str, ranks)),
                actual_first_bike=actual[0], actual_second_bike=actual[1], actual_third_bike=actual[2],
                actual_first_pred_rank=ranks[0], actual_second_pred_rank=ranks[1], actual_third_pred_rank=ranks[2],
                exacta_rank_pattern='>'.join(map(str, ranks[:2])), trifecta_rank_pattern='>'.join(map(str, ranks[:3])))
            for prefix, key, n in [('nisyatan','exacta',2), ('sanrentan','trifecta',3)]:
                pay = payouts.get(rid, {})
                combo = tuple(map(int, re.findall(r'\d+', str(pay.get(prefix+'_combo', '')))))
                value = pay.get(prefix+'_payout')
                ok = combo == tuple(actual[:n]) and isinstance(value, (int,float)) and math.isfinite(value) and value >= 100
                row[key+'_payout_verified'] = ok
                if ok: row[key+'_payout_yen_per_100'] = value
                elif combo and combo != tuple(actual[:n]): issues.append(dict(race_id=rid, issues=[key+'_payout_combo_mismatch']))
            # Independent round-trip: rank sequence reconstructs actual bike sequence exactly.
            assert [bikes[r-1] for r in ranks] == actual
        records.append(row)

records.sort(key=lambda r:(r['date'], r['race_id']))
dumpcsv('race_rank_outcomes.csv', records)
byid = {r['race_id']:r for r in records}
checks, mismatches = collections.Counter(), []
for suffix in ['_ledger.csv', '_october_additional_ledger.csv']:
    for prior in csv.DictReader((BASE/(MODEL+suffix)).open()):
        r = byid[prior['race_id']]
        for market in json.loads(prior['markets']):
            n = 2 if market['market']=='exacta' else 3
            got = '>'.join(r['actual_bikes'].split('>')[:n])
            checks[market['market']] += 1
            if r['outcome_status'] != 'ok' or got != market['actual']:
                mismatches.append(dict(race_id=r['race_id'], market=market['market'], expected=market['actual'], got=got))
assert not mismatches, mismatches[:10]

counts, totals = collections.Counter(), collections.Counter()
for r in records:
    if r['outcome_status'] != 'ok': continue
    for market, band, field in [('exacta',r['exacta_band'],'exacta_rank_pattern'),('trifecta',r['trifecta_band'],'trifecta_rank_pattern')]:
        for phase in [r['phase'], 'all_recorded_periods']:
            group=(phase, market, band, r['rider_count'])
            totals[group]+=1
            counts[group+(r[field],)]+=1
patterns=[]
for key,n in sorted(counts.items()):
    phase,market,band,nr,pattern=key
    patterns.append(dict(phase=phase,market=market,band=band,rider_count=nr,rank_pattern=pattern,
                         count=n,group_races=totals[key[:-1]],frequency=n/totals[key[:-1]]))
dumpcsv('rank_pattern_counts.csv', patterns)
assert sum(v for (phase,market,*_),v in counts.items() if phase=='all_recorded_periods' and market=='exacta') == sum(r['outcome_status']=='ok' for r in records)

summary=dict(model=MODEL,model_sha256=MODEL_SHA,source_commit=SOURCE_COMMIT,
             period_start=records[0]['date'],period_end=records[-1]['date'],records=len(records),
             outcome_status=dict(collections.Counter(r['outcome_status'] for r in records)),
             exacta_bands=dict(collections.Counter(r['exacta_band'] for r in records)),
             trifecta_bands=dict(collections.Counter(r['trifecta_band'] for r in records)),
             phases=dict(collections.Counter(r['phase'] for r in records)),
             exacta_payout_verified=sum(r['exacta_payout_verified'] for r in records),
             trifecta_payout_verified=sum(r['trifecta_payout_verified'] for r in records),
             prior_ledger_checks=dict(checks),prior_ledger_mismatches=mismatches,issues=issues,
             input_files=inputs,purchase_or_odds_filter_applied=False,production_changed=False,
             band_definition=dict(exacta=EX_BANDS,exacta_fallback='LOW',trifecta=TRI_BANDS,trifecta_fallback='S3-LOW'),
             limitations=['Retrospective archived inputs, not timestamped pre-race captures.',
                          'Research model, not production fixed model.',
                          'Descriptive outcome record, not a new independent holdout or evidence of positive expected value.',
                          'Band labels reflect frozen score thresholds, not grade-based purchase permission. F2 retained.',
                          'Missing/unverified payouts do not remove an otherwise verifiable finish record.'])
summary['output_sha256']={p.name:sha(p) for p in OUT.glob('*.csv')}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print('RANK_OUTCOMES_RECORDED',json.dumps({k:summary[k] for k in ['records','outcome_status','exacta_bands','trifecta_bands','phases','prior_ledger_checks','exacta_payout_verified','trifecta_payout_verified']},ensure_ascii=False),flush=True)
