"""Find whether existing fixed HaruQ HIGH tickets can be bought profitably without retraining.
Exploratory temporal hold-forward only; no production policy change.
"""
from __future__ import annotations
import collections,csv,json,itertools,math
from pathlib import Path
import scripts.audit_final_day_odds4_20261026 as B
OUT=Path("research_audits/high_purchase_research_20261026")
OUT.mkdir(parents=True,exist_ok=True)
by_id={str(x["race_id"]):x for x in csv.DictReader(B.LEDGER.open(encoding="utf-8",newline=""))}
assert len(B.selected)==1800,(len(B.selected),B.summary(B.selected))
all_final=B.selected
all_nonfinal=[x for x in B.allrows if not B.mark_final(x["race_id"])]
def phase(d):return "2025H2" if d<"2026-01-01" else "2026H1"
def quarter(d):return d[:4]+"Q"+str((int(d[5:7])-1)//3+1)
def metric(rs):
    r=list(rs)
    st=sum(x["stake"] for x in r);ret=sum(x["paid"] for x in r)
    return dict(tickets=len(r),stake=st,paid=ret,profit=ret-st,
                roi_pct=round(100*ret/st,3) if st else None,
                hits=sum(x["paid"]>0 for x in r),
                races=len({x["race_id"] for x in r}))
def trows(races):
    for rr in races:
        base=by_id[rr["race_id"]];gap=float(base["gap"])
        for m in rr["markets"]:
            ts=m["tickets"];assert int(m["stake"])==500*len(ts)
            actual=str(m["actual"]).replace("- ",">").replace("-",">")
            accrued=0
            for i,t in enumerate(ts,1):
                win=(str(t)==actual)
                paid=int(m["paid"]) if win else 0
                accrued+=paid
                yield dict(race_id=rr["race_id"],date=rr["date"],
                    phase=phase(rr["date"]),quarter=quarter(rr["date"]),
                    grade=rr["grade"],gap=gap,market=m["market"],
                    rank=i,ticket=str(t),stake=500,paid=paid)
            assert accrued==int(m["paid"]),(rr["race_id"],m["market"],actual,ts)
final=list(trows(all_final))
nonfinal=list(trows(all_nonfinal))
assert metric(final)["stake"]==4179000
assert metric(final)["paid"]==3976750
assert metric(nonfinal)["stake"]==19330000-4179000
assert metric(nonfinal)["paid"]==17926550-3976750
ex=[x for x in final if x["market"]=="exacta"]
tri=[x for x in final if x["market"]=="trifecta"]
def summarize_condition(rows,func=lambda x:True):
    r=[x for x in rows if func(x)]
    return {"overall":metric(r),
     "early":metric(x for x in r if x["phase"]=="2025H2"),
     "later":metric(x for x in r if x["phase"]=="2026H1"),
     "quarters":{q:metric(x for x in r if x["quarter"]==q)
                 for q in ["2025Q3","2025Q4","2026Q1","2026Q2"]}}
stats={
 "baseline":summarize_condition(final),
 "exacta_only":summarize_condition(ex),
 "trifecta_only":summarize_condition(tri),
 "individual_rank":{
    "exacta":{str(i):summarize_condition(ex,lambda x,i=i:x["rank"]==i) for i in range(1,5)},
    "trifecta":{str(i):summarize_condition(tri,lambda x,i=i:x["rank"]==i) for i in range(1,7)}},
 "grades":{g:summarize_condition(final,lambda x,g=g:x["grade"]==g) for g in sorted({x["grade"] for x in final})},
 "scoregap":{g:summarize_condition(final,lambda x,lo=lo,hi=hi:lo<=x["gap"]<hi)
    for g,lo,hi in [("1.0-1.25",1,1.25),("1.25-1.5",1.25,1.5),("1.5-2.0",1.5,2),("2.0-2.5",2,2.5),("2.5+",2.5,1e10)]},
 "nonfinal_check":summarize_condition(nonfinal)
}
def _r(x):return x["rank"]
# Predeclared small transparent family of selectable tickets and filters:
# 4 exacta cuts, 2 triple cut variants, gap bands and major grades.
# Search early period only (July-Dec 2025); evaluate selected rule in next half.
candidates=[]
grades={"any":None,"F1":{"F1"},"F2":{"F2"},"G3":{"G3"},"F1_F2":{"F1","F2"}}
gapfloor={"1.0":1.0,"1.25":1.25,"1.5":1.5,"2.0":2.0,"2.5":2.5}
ticket_sets={
  "all_original":dict(ex=set(range(1,5)),tr=set(range(1,7))),
  "exacta_all":dict(ex=set(range(1,5)),tr=set()),
  "exacta_first3":dict(ex={1,2,3},tr=set()),
  "exacta_first2":dict(ex={1,2},tr=set()),
  "exacta_first":dict(ex={1},tr=set()),
  "exacta_second":dict(ex={2},tr=set()),
  "exacta_third":dict(ex={3},tr=set()),
  "exacta_fourth":dict(ex={4},tr=set()),
  "trifecta_all":dict(ex=set(),tr=set(range(1,7))),
  "exacta_first2_plus_trifecta":dict(ex={1,2},tr=set(range(1,7))),
}
for (g,grade_set),(fl,minimum),(tk,cuts) in itertools.product(grades.items(),gapfloor.items(),ticket_sets.items()):
    if tk=="trifecta_all" and minimum<2:continue
    def included(x):
        if x["gap"]<minimum:return False
        if grade_set is not None and x["grade"] not in grade_set:return False
        return x["rank"] in (cuts["ex"] if x["market"]=="exacta" else cuts["tr"])
    item=summarize_condition(final,included)
    candidates.append(dict(grade=g,gap_floor=fl,ticket_rule=tk,**item))
# Ranked solely by early-period outcomes; next-half metrics are not used for candidate selection.
eligible=[c for c in candidates if c["early"]["stake"]>=100000 and c["early"]["races"]>=50]
ranked=sorted(eligible,key=lambda c:(c["early"]["roi_pct"],c["early"]["profit"]),reverse=True)
chosen=ranked[:12]
# Exhaustive stability diagnostics should not imply a selection rule has proven positive expectancy.
positive_in_both=[c for c in candidates
                  if c["early"]["stake"]>=100000 and c["later"]["stake"]>=100000
                  and c["early"]["roi_pct"]>100 and c["later"]["roi_pct"]>100]
positive_both_sorted=sorted(positive_in_both,key=lambda c:min(c["early"]["stake"],c["later"]["stake"]),reverse=True)
bytype=collections.Counter(x["market"] for x in final)
result=dict(
 method="Read-only frozen HIGH ticket ablations; meeting-final confirmation exactly as baseline; 2025H2 discovery / 2026H1 temporal diagnostic; latter previously viewed not untouched. Historical archive odds not used.",
 frozen_model_sha256=B.ref["fixed_model_sha256"], 
 validation={"selected_races":len(all_final),"ticket_lines":len(final),
   "stake":metric(final)["stake"],"paid":metric(final)["paid"],
   "market_counts":dict(bytype)},
 statistics=stats,
 candidate_design={"grade":list(grades),"gap_floors":list(gapfloor),
    "ticket_rules":list(ticket_sets),"generated":len(candidates),
    "early_min_stake":100000,"early_min_races":50,
    "eligible_in_discovery":len(eligible)},
 best_early_chosen=chosen,
 positive_in_both_count=len(positive_in_both),
 positive_in_both=positive_both_sorted[:20],
 caution="Exploratory multiple comparisons; no rule validated on genuinely unseen future period. Do not silently change production, ticket amounts, criteria or predictability.")
(OUT/"high_purchase_stability.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
with (OUT/"all_candidate_ablation.csv").open("w",encoding="utf-8",newline="") as f:
 w=csv.DictWriter(f,fieldnames=["grade","gap_floor","ticket_rule","early_races","early_stake","early_paid","early_profit","early_roi_pct","later_races","later_stake","later_paid","later_profit","later_roi_pct"])
 w.writeheader()
 for c in candidates:
  w.writerow({**{key:c[key] for key in ["grade","gap_floor","ticket_rule"]},
      **{phase+"_"+field:c[period][field] for phase,period in [("early","early"),("later","later")] for field in ["races","stake","paid","profit","roi_pct"]}})
print("HIGH_PURCHASE_RESEARCH",json.dumps({"base":stats["baseline"],"position":{k:{i:v["overall"] for i,v in d.items()} for k,d in stats["individual_rank"].items()},"discovery_winners":chosen[:8],"positive_in_both":positive_both_sorted[:12],"counts":result["candidate_design"]},ensure_ascii=False),flush=True)
