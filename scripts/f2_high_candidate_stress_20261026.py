"""F2 HIGH focused stress checks, no production changes."""
import collections,json,random
from pathlib import Path
import scripts.research_f2_high_purchase_20261026 as F
OUT=Path("research_audits/f2_high_purchase_20261026")
C=[
 ("A_rank3_4_5_gap1_5",{"ex":{2,3,4},"tri":set(),"gap":1.5}),
 ("B_rank3_4_gap2",{"ex":{2,3},"tri":set(),"gap":2.0}),
 ("C_rank3_4_allHIGH",{"ex":{2,3},"tri":set(),"gap":1.0}),
 ("D_exacta4_allHIGH",{"ex":{1,2,3,4},"tri":set(),"gap":1.0}),
 ("E_original",{"ex":{1,2,3,4},"tri":{1,2,3,4,5,6},"gap":1.0}),
 ("F_rank3_only_gap2",{"ex":{2},"tri":set(),"gap":2.0}),
 ("G_rank3_4_5_allHIGH",{"ex":{2,3,4},"tri":set(),"gap":1.0}),
 ("H_exacta4_gap1_5",{"ex":{1,2,3,4},"tri":set(),"gap":1.5}),
]
def details(rows,seed):
 stat=F.summarize(rows);months=sorted({x["date"][:7] for x in rows})
 by_month={m:F.summarize(x for x in rows if x["date"][:7]==m) for m in months}
 by_race=collections.defaultdict(lambda:{"stake":0,"paid":0})
 by_day=collections.defaultdict(lambda:{"stake":0,"paid":0})
 for x in rows:
  for target,key in [(by_race,x["race_id"]),(by_day,x["date"]+"-"+x["race_id"][8:10])]:
   target[key]["stake"]+=x["stake"];target[key]["paid"]+=x["paid"]
 wins=sorted(by_race.items(),key=lambda q:q[1]["paid"],reverse=True)
 def trimmed(n):
  rem=wins[:n];st=stat["stake"]-sum(v["stake"] for _,v in rem)
  pd=stat["paid"]-sum(v["paid"] for _,v in rem)
  return {"stake":st,"paid":pd,"profit":pd-st,"roi_pct":round(100*pd/st,3) if st else None}
 rnd=random.Random(seed);groups=list(by_day.values())
 if groups:
  b=[]
  for _ in range(3000):
   sample=[groups[rnd.randrange(len(groups))] for _ in groups]
   st=sum(x["stake"] for x in sample);paid=sum(x["paid"] for x in sample)
   b.append(100*paid/st if st else 0)
  b.sort()
  boot={"95pct":[round(b[75],2),round(b[2924],2)],"simulations":3000}
 else:boot=None
 return {"totals":stat,"monthly":by_month,
         "max_single_payout":max([v["paid"] for v in by_race.values()],default=0),
         "top3_payout_share":round(sum(x[1]["paid"] for x in wins[:3])/stat["paid"]*100,2) if stat["paid"] else None,
         "excluding_top1_race":trimmed(1),"excluding_top3_races":trimmed(3),
         "venue_days":len(groups),"venue_day_bootstrap":boot}
out={"scope":"Read-only archived fixed F2 HIGH ticket structures. All final days confirmed from calendar source. Comparison other days descriptive, not unseen validation.","candidates":{}}
for i,(key,c) in enumerate(C):
 last=F.filt(F.rows,c["ex"],c["tri"],c["gap"])
 other=F.filt(F.nonfinal,c["ex"],c["tri"],c["gap"])
 out["candidates"][key]={"rule":{"exacta_ranks":sorted(c["ex"]),"trifecta_positions":sorted(c["tri"]),"gap_floor":c["gap"]},
     "final_day":details(last,20261026+i),"other_meeting_days":details(other,20261076+i)}
(OUT/"f2_focused_robustness.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
print("F2_FOCUSED_ROBUSTNESS",json.dumps({k:{"final_day":v["final_day"],"nonfinal":v["other_meeting_days"]["totals"]} for k,v in out["candidates"].items()},ensure_ascii=False),flush=True)
