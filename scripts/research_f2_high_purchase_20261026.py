"""F2 HIGH only: retrospective purchase-composition audit on confirmed final days.
No production, ranking, or historical inputs changed.
"""
import collections, csv, itertools, json, math, random
from pathlib import Path
import scripts.research_high_purchase_experiment_20261026 as P

OUT=Path("research_audits/f2_high_purchase_20261026")
OUT.mkdir(parents=True,exist_ok=True)
rows=[x for x in P.final if x["grade"]=="F2"]
nonfinal=[x for x in P.nonfinal if x["grade"]=="F2"]
assert len({x["race_id"] for x in rows})==448
assert P.metric(rows)["stake"]==1190000
assert P.metric(rows)["paid"]==1143500

def summarize(xs):
 xs=list(xs);st=sum(x["stake"] for x in xs);pd=sum(x["paid"] for x in xs)
 return dict(races=len({x["race_id"] for x in xs}),tickets=len(xs),
             stake=st,paid=pd,profit=pd-st,roi_pct=round(pd/st*100,3) if st else None,
             hit_tickets=sum(x["paid"]>0 for x in xs))
def month(x): return x["date"][:7]
def filt(allrows,ex,tri,gaplo=1.,gaphi=float("inf")):
 return [x for x in allrows if gaplo<=x["gap"]<gaphi and
  (x["rank"] in (ex if x["market"]=="exacta" else tri))]
def profile(src,ex,tri,gaplo=1.,gaphi=float("inf")):
 kept=filt(src,ex,tri,gaplo,gaphi)
 return dict(all=summarize(kept),monthly={m:summarize(x for x in kept if month(x)==m)
   for m in sorted({month(x) for x in kept})},
   by_market={k:summarize(x for x in kept if x["market"]==k) for k in ["exacta","trifecta"]})

head={
 "eligible_F2_finalday":summarize(rows),
 "date_range":[min(x["date"] for x in rows),max(x["date"] for x in rows)],
 "baseline_monthly":profile(rows,set(range(1,5)),set(range(1,7)))["monthly"],
 "exacta_slots":{str(i):profile(rows,{i},set()) for i in range(1,5)},
 "trifecta_slots":{str(i):profile(rows,set(),{i}) for i in range(1,7)},
 "nonfinal_baseline":summarize(nonfinal),
}
# Market candidate sets are determined by pre-existing slot order, not outcomes.
E={
 "E0_none":set(),
 "E1_rank2":{1},
 "E2_rank3":{2},
 "E3_rank4":{3},
 "E4_rank5":{4},
 "E12_rank2_3":{1,2},
 "E13_rank2_4":{1,3},
 "E14_rank2_5":{1,4},
 "E23_rank3_4":{2,3},
 "E24_rank3_5":{2,4},
 "E34_rank4_5":{3,4},
 "E123_rank2_3_4":{1,2,3},
 "E124_rank2_3_5":{1,2,4},
 "E134_rank2_4_5":{1,3,4},
 "E234_rank3_4_5":{2,3,4},
 "E1234_all":{1,2,3,4}}
T={
 "T0_none":set(),
 "T_all6":set(range(1,7)),
 "T_first3":{1,2,3},
 "T_last3":{4,5,6},
 "T_12":{1,2},
 "T_34":{3,4},
 "T_56":{5,6},
 "T_135":{1,3,5},
 "T_246":{2,4,6},
 "T_1234":{1,2,3,4},
 "T_3456":{3,4,5,6},
 }
# Second- and third-place rank pairs are tracked by frozen permutation order.
firsttri=next(x for x in rows if x["market"]=="trifecta")["race_id"]
ledger=P.by_id[firsttri]
tri_order=next(m["tickets"] for m in json.loads(ledger["markets"]) if m["market"]=="trifecta")
ranked=[str(x) for x in next(m["tickets"] for m in json.loads(ledger["markets"]) if m["market"]=="exacta")]
# Derive reciprocal slots from second/third bike combinations, never presume 1,2,3 ordering.
rev={}
for i,t in enumerate(tri_order,1):
 a,b,c=t.split(">")
 rev[(b,c)]=i
for i,t in enumerate(tri_order,1):
 a,b,c=t.split(">")
 assert rev.get((c,b)) is not None
# For every race, permutation order is generated from frozen rank2,3,4,
# so these structural slot indices are invariant even when bike numbers vary.
T["T_reciprocal23"]={1,3}
T["T_reciprocal24"]={2,5}
T["T_reciprocal34"]={4,6}
# Full family of allowed mix-and-match structural ticket subsets;
# do not use holdout outcomes to pick rules.
candidates=[]
for (ename,ex),(tname,tri),gap in itertools.product(E.items(),T.items(),[1.0,1.25,1.5,2.0]):
 if not ex and not tri:continue
 if not ex and gap<2:continue
 selected=filt(rows,ex,tri,gap)
 if len(selected)==0:continue
 item=dict(exacta_rule=ename,trifecta_rule=tname,gap_floor=gap,
           overall=summarize(selected),
           monthly={m:summarize(x for x in selected if month(x)==m) for m in sorted({month(x) for x in selected})})
 candidates.append(item)
months=sorted({month(x) for x in rows})
head["months"]=months
# Natural chronological split: January+February -> March, requiring meaningful stakes.
cal_dates={m:[x for x in rows if month(x)==m] for m in months}
def pret(a):
 return [x for x in a if month(x)!="2026-03"]
def post(a):
 return [x for x in a if month(x)=="2026-03"]
for c in candidates:
 chosen=filt(rows,E[c["exacta_rule"]],T[c["trifecta_rule"]],c["gap_floor"])
 c["discovery_JanFeb"]=summarize(pret(chosen))
 c["check_Mar"]=summarize(post(chosen))
 if c["overall"]["stake"]>0:
  c["win_payout_concentration"]=round(max([x["paid"] for x in chosen],default=0)/c["overall"]["paid"]*100,2) if c["overall"]["paid"]>0 else 0.
eligible=[x for x in candidates if x["discovery_JanFeb"]["stake"]>=30000 and x["discovery_JanFeb"]["races"]>=30]
earlyranked=sorted(eligible,key=lambda v:(v["discovery_JanFeb"]["roi_pct"],v["discovery_JanFeb"]["stake"]),reverse=True)
# Better-supported options sorted solely using January+February, March displayed for falsification.
top_janfeb=earlyranked[:20]
larger=[c for c in candidates if c["overall"]["stake"]>=100000 and c["overall"]["races"]>=120]
top_full=sorted(larger,key=lambda c:c["overall"]["roi_pct"],reverse=True)[:20]
both=[c for c in candidates if c["discovery_JanFeb"]["stake"]>=30000 and c["check_Mar"]["stake"]>=15000
      and c["discovery_JanFeb"]["roi_pct"]>100 and c["check_Mar"]["roi_pct"]>100]
both=sorted(both,key=lambda c:(c["overall"]["stake"],c["overall"]["roi_pct"]),reverse=True)
# Rank and exacta-vs-tri outcome by month, plus the unfiltered F2 across *all* days.
out={
 "method":"Read-only frozen HaruQ F2 HIGH, confirmed final days, outcomes and 500yen-per-ticket actual dividends",
 "counts":head,
 "candidate_family":{"exacta":{k:sorted(v) for k,v in E.items()},
   "trifecta":{k:sorted(v) for k,v in T.items()},"floor":[1,1.25,1.5,2],
   "evaluated":len(candidates),"JanFeb_min_stake":30000,
   "March_check_status":"The same historical holdout previously inspected; not independent untouched out-of-sample"},
 "top_20_discovery_JanFeb":top_janfeb,
 "top_20_full_sample_with_100k_stake":top_full,
 "both_JanFeb_and_March_positive_supported":both[:25],
 "both_positive_count":len(both),
 "limitations":["F2 archive covers 2026 Q1 only.","Many candidate tests, selection-bias risk.","Individual exacta losing odds not archived; no 4.0x filter applied.","No model/policy alteration."] }
(OUT/"f2_high_purchase_results.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
with (OUT/"f2_high_candidate_family.csv").open("w",newline="",encoding="utf-8") as f:
 fields=["exacta_rule","trifecta_rule","gap_floor","overall_races","overall_stake","overall_paid","overall_profit","overall_roi_pct","discovery_JanFeb_races","discovery_JanFeb_stake","discovery_JanFeb_profit","discovery_JanFeb_roi_pct","check_Mar_races","check_Mar_stake","check_Mar_profit","check_Mar_roi_pct"]
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
 for c in candidates:
  w.writerow({**{k:c[k] for k in ["exacta_rule","trifecta_rule","gap_floor"]},
    **{phase+"_"+k:v[k] for phase in ["overall","discovery_JanFeb","check_Mar"]
       for k in (["races","stake","paid","profit","roi_pct"] if phase=="overall" else ["races","stake","profit","roi_pct"])
       for v in [c[phase]]}})
print("F2_HIGH_PURCHASE_SCAN",json.dumps({"baseline":head["eligible_F2_finalday"],"months":head["baseline_monthly"],
 "slots":{k:{i:v["all"] for i,v in head[k].items()} for k in ["exacta_slots","trifecta_slots"]},
 "top_early":top_janfeb[:8],"full":top_full[:5],"both":both[:8],
 "tested":len(candidates)},ensure_ascii=False),flush=True)
