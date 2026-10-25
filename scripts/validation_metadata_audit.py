import ast,collections,csv,json,re,sqlite3
from pathlib import Path

out=Path('metadata_audit');out.mkdir(exist_ok=True)
con=sqlite3.connect('db/keirin.db');con.row_factory=sqlite3.Row
tree=ast.parse(Path('research_snapshots/haruqube_20260321/config.py').read_text())
classes=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CLASS_MAP' for t in n.targets))
meta={r['race_id']:dict(r) for r in con.execute("SELECT race_id,date,grade,race_name FROM races WHERE date>='2025-07-01' AND date<'2026-10-01'")}
entries=collections.defaultdict(list)
for r in con.execute("SELECT e.* FROM entries e JOIN races r USING(race_id) WHERE r.date>='2025-07-01' AND r.date<'2026-10-01'"):entries[r['race_id']].append(dict(r))
results=collections.defaultdict(list)
for r in con.execute("SELECT rr.race_id,rr.rider_id,rr.class,rr.line_group,rr.finish_position FROM race_results rr JOIN races r USING(race_id) WHERE rr.finish_position IS NOT NULL ORDER BY r.date"):
 if r['race_id'] in meta:results[r['race_id']].append(dict(r))
selected={r['race_id'] for r in csv.DictReader(open('research_audits/validation_parity_20261025/current_policy_ledger.csv'))}
def reject(rows,name):
 return bool(rows) and (all(r['class'] is None for r in rows) or any(str(r['class'] or '').upper().startswith('L') for r in rows) or bool(re.search('ガールズ|ガール|ガ決|ガ般|Ｌ級|L級',name or '')))
def valid(rows):
 pos=[r['finish_position'] for r in rows]
 return len(rows)>=5 and len(set(pos))==len(pos) and pos.count(1)==1 and None not in pos
comparisons=[];ties=[]
for rid,rs in results.items():
 if not valid(rs):continue
 es=entries[rid];name=meta[rid]['race_name'];a=reject(rs,'');b=reject(es,name)
 comparisons.append(dict(race_id=rid,grade=meta[rid]['grade'],result_rejected=a,entry_rejected=b,entry_count=len(es),result_classes=[r['class'] for r in rs],entry_classes=[r['class'] for r in es],selected=rid in selected))
 groups=collections.defaultdict(list)
 for r in rs:
  if r['line_group']:groups[r['line_group']].append(r)
 if not groups:continue
 scores={k:sum(7-classes.get(r['class'],6) for r in v) for k,v in groups.items()};best=max(scores.values());tops=[k for k,v in scores.items() if v==best]
 if len(tops)<2:continue
 chosen=max(scores,key=scores.get);win=next(r for r in rs if r['finish_position']==1)
 ties.append(dict(race_id=rid,result_rejected=a,selected=rid in selected,tied_lines=len(tops),winner_line_is_tied=win['line_group'] in tops,winner_line_chosen=win['line_group']==chosen,first_row_is_winner=rs[0]['finish_position']==1))
def ts(rows):
 return dict(races=len(rows),winner_line_chosen=sum(r['winner_line_chosen'] for r in rows),winner_line_chosen_pct=100*sum(r['winner_line_chosen'] for r in rows)/len(rows) if rows else None,first_row_is_winner=sum(r['first_row_is_winner'] for r in rows))
report=dict(valid_races=len(comparisons),no_entries=sum(not r['entry_count'] for r in comparisons),result_excluded=sum(r['result_rejected'] for r in comparisons),entry_excluded=sum(r['entry_rejected'] for r in comparisons),eligibility_mismatch=[r for r in comparisons if r['result_rejected']!=r['entry_rejected']],by_grade={g:dict(races=sum(r['grade']==g for r in comparisons),result_excluded=sum(r['grade']==g and r['result_rejected'] for r in comparisons),entry_excluded=sum(r['grade']==g and r['entry_rejected'] for r in comparisons)) for g in sorted({r['grade'] for r in comparisons})},tie_diagnostic=dict(all=ts(ties),eligible=ts([r for r in ties if not r['result_rejected']]),selected=ts([r for r in ties if r['selected']])),selected_rejection_cases=[r for r in comparisons if r['selected'] and r['entry_rejected']])
(out/'metadata_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
(out/'eligibility_rows.json').write_text(json.dumps(comparisons,ensure_ascii=False))
(out/'tie_rows.json').write_text(json.dumps(ties,ensure_ascii=False))
print('METADATA_AUDIT_COMPLETE',json.dumps(report,ensure_ascii=False),flush=True)
