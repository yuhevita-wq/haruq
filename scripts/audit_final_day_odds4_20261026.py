"""Read-only HaruQ final-day audit. Production and betting policy remain unchanged."""
import collections
import csv
import datetime as dt
import decimal
import gzip
import hashlib
import json
import sqlite3
from pathlib import Path

OUT=Path("research_audits/final_day_4x_20261026")
OUT.mkdir(parents=True,exist_ok=True)
LEDGER=Path("research_audits/validation_parity_20261025/current_policy_ledger.csv")
START,END="2025-07-01","2026-09-30"
def summary(items):
    x=list(items)
    stake=sum(i["stake"] for i in x)
    paid=sum(i["paid"] for i in x)
    return {"races":len(x),"stake":stake,"paid":paid,
            "profit":paid-stake,"roi_pct":round(100*paid/stake,5) if stake else None,
            "winning_races":sum(i["paid"]>0 for i in x)}
def basic(m):
    return {"stake":m["stake"],"paid":m["paid"]}
def netid(source):
    # Source ID venue(2)+meeting start(8)+ordinal(2)+race no(4)
    assert len(source)==16 and source.isdigit()
    d=dt.datetime.strptime(source[2:10],"%Y%m%d").date()
    day=d+dt.timedelta(days=int(source[10:12])-1)
    return day.strftime("%Y%m%d")+source[:2]+f"{int(source[12:16]):02d}"
con=sqlite3.connect("file:db/keirin.db?mode=ro",uri=True)
con.row_factory=sqlite3.Row
races={str(x["race_id"]):dict(x) for x in con.execute(
    "SELECT race_id,date,grade,round,race_name,velodrome FROM races WHERE date>=? AND date<=?",(START,END))}
# The only acceptable positive final-day proof here is an explicit final race in the
# stored race schedule/result classification. Never infer final day from "last observed date."
confirmed=collections.defaultdict(set)
for rid,meta in races.items():
    if "決勝" in str(meta.get("round") or "") or "決勝" in str(meta.get("race_name") or ""):
        confirmed[(meta["date"],rid[8:10])].add(rid)
# Independent published programme classification preserved in odds-only
# archives, keyed by meeting start and day number. "決勝" is direct
# race-programme evidence of the meeting's final day; no presumed duration.
for year in (2025, 2026):
    with gzip.open(f"odds_{year}.jsonl.gz", "rt", encoding="utf-8") as calendar_stream:
        for line in calendar_stream:
            event=json.loads(line)
            if "決勝" not in str(event.get("race_type") or ""): continue
            event_id=netid(str(event["race_id"]))
            if event_id not in races: continue
            confirmed[(event_id[:8][:4]+"-"+event_id[4:6]+"-"+event_id[6:8],event_id[8:10])].add(event_id)
assert confirmed, "No final-round evidence from race metadata or published programme archive"
def mark_final(rid):
    m=races.get(rid)
    return m is not None and (m["date"],rid[8:10]) in confirmed
allrows=[]
for x in csv.DictReader(LEDGER.open(encoding="utf-8",newline="")):
    rid=str(x["race_id"])
    assert START <= x["date"] <= END
    markets=json.loads(x["markets"])
    assert int(x["stake"]) == sum(int(m["stake"]) for m in markets)
    assert int(x["paid"]) == sum(int(m["paid"]) for m in markets)
    allrows.append({"race_id":rid,"date":x["date"],"grade":x["grade"],
       "stake":int(x["stake"]),"paid":int(x["paid"]),"markets":markets})
assert summary(allrows)["races"]==7448, summary(allrows)
assert summary(allrows)["stake"]==19330000, summary(allrows)
assert summary(allrows)["paid"]==17926550, summary(allrows)
selected=[x for x in allrows if mark_final(x["race_id"])]
no_meta=[x["race_id"] for x in allrows if x["race_id"] not in races]
ref={}
ref["source_ledger"]="research_audits/validation_parity_20261025/current_policy_ledger.csv"
ref["fixed_model_sha256"]="e70690f4538b77e927a042e7ae2db312f8a0a4f16bf72def37e7ccad3568c193"
ref["holdout"]={"start":START,"end":END,"all_eligible":summary(allrows)}
ref["finalday"]={"proof":"Exact final-round race on same day and venue, from official programme label in independent archived odds where primary SQLite round metadata is null; no max-observed-date shortcut",
                 "confirmed_venue_days":len(confirmed),
                 "selected":summary(selected),
                 "excluded_unconfirmed":len(allrows)-len(selected),
                 "missing_metadata_count":len(no_meta),
                 "diagnostic_round_counts":dict(collections.Counter(str(m.get("round")) for m in races.values()).most_common(12)),
                 "monthly":{k:summary(v) for k,v in sorted({r["date"][:7]:[x for x in selected if x["date"][:7]==r["date"][:7]] for r in selected}.items())}}
ref["finalday"]["by_market"]={}
for market in ["exacta","trifecta"]:
    rows=[]
    for r in selected:
        for m in r["markets"]:
            if m["market"]==market:rows.append({"stake":int(m["stake"]),"paid":int(m["paid"])})
    ref["finalday"]["by_market"][market]=summary(rows)
ref["finalday"]["by_grade"]={}
for grade in sorted({r["grade"] for r in selected}):
    ref["finalday"]["by_grade"][grade]=summary(x for x in selected if x["grade"]==grade)
(OUT/"lastday_baseline.json").write_text(json.dumps(ref,ensure_ascii=False,indent=2)+"\n")
print("HARUQ_FINAL_DAY_BASELINE",json.dumps({
    "baseline":ref["finalday"]["selected"],
    "markets":ref["finalday"]["by_market"],
    "confirmed_venue_days":len(confirmed),
    "unconfirmed_selected":len(allrows)-len(selected)},ensure_ascii=False),flush=True)

# Public archived odds universe contains all 3連単/3連複 quotes for 2025 and
# 2026H1 only, NOT 2車単 or 2026Q3. Do not silently treat partial odds as complete.
allowed={r["race_id"]:r for r in selected if r["date"]<"2026-07-01"}
raw=collections.defaultdict(list)
reading=collections.Counter()
for year in [2025,2026]:
    path=Path(f"odds_{year}.jsonl.gz")
    h=hashlib.sha1(b"blob "+str(path.stat().st_size).encode()+b"\0"+path.read_bytes()).hexdigest()
    known={2025:"53eb48b44a898a3c8f030b5071d95ed74550197a",2026:"eebf1193a15384d94022d8640b2dc851d2c91f55"}
    assert h==known[year],(year,h)
    with gzip.open(path,"rt",encoding="utf-8") as stream:
        for line in stream:
            rec=json.loads(line,parse_float=decimal.Decimal)
            rid=netid(str(rec["race_id"]))
            if rid not in allowed:continue
            reading["source_match_rows"]+=1
            quotes=rec.get("odds",{}).get("3連単")
            if not isinstance(quotes,dict):continue
            raw[rid].append((str(rec["race_id"]),quotes))
            reading["trifecta_source_matched"]+=1
tri_valid=[]
rejections=collections.Counter()
for rid,r in allowed.items():
    m=next((x for x in r["markets"] if x["market"]=="trifecta"),None)
    if not m:continue
    options=raw.get(rid,[])
    if len(options)!=1:
        rejections["missing_or_duplicate_quote_record"]+=1;continue
    src,qq=options[0]
    keys={str(k):decimal.Decimal(str(v)) for k,v in qq.items()}
    tickets=[str(t).replace(">","-") for t in m["tickets"]]
    if not all(t in keys and keys[t]>=1 and keys[t].is_finite() for t in tickets):
        rejections["missing_or_invalid_ticket_quotes"]+=1;continue
    win=str(m["actual"]).replace(">","-")
    if win not in keys:
        rejections["winning_quote_missing"]+=1;continue
    # If winning 3連単 is one of original six tickets, compare the exact
    # final quoted odds to actual archived payouts. Discrepancies quarantined.
    if int(m["paid"])>0 and decimal.Decimal(int(m["paid"])) != keys[win]*500:
        rejections["winning_quote_payout_disagreement"]+=1;continue
    keep=[t for t in tickets if keys[t]>=decimal.Decimal("4.0")]
    newstake=500*len(keep)
    newpaid=int(m["paid"]) if win in keep else 0
    original_paid=int(m["paid"])
    tri_valid.append({"race_id":rid,"date":r["date"],"source_id":src,
        "stake":newstake,"paid":newpaid,
        "original_stake":int(m["stake"]),"original_paid":original_paid,
        "kept":len(keep),"omitted":len(tickets)-len(keep)})
s0=summary({"stake":r["original_stake"],"paid":r["original_paid"]} for r in tri_valid)
s1=summary(tri_valid)
ref["odds4_partial"]={
  "status":"PARTIAL_ONLY__NOT_USER_REQUESTED_COMBINED_RESULT",
  "source":"yuhevita-wq/keirin-market-analysis-/data/odds_only",
  "coverage":"3連単 final odds only; up to 2026-06-30, NO 2車単 all-ticket quotes, NO 2026Q3",
  "qualifying_final_day_trifecta_races_through_20260630":sum(any(m["market"]=="trifecta" for m in r["markets"]) for r in allowed.values()),
  "verified_races":len(tri_valid),
  "rejections":dict(rejections),
  "before_4x":s0,
  "after_excluding_below_4x":s1,
  "removed_tickets":sum(x["omitted"] for x in tri_valid),
  "stayed_tickets":sum(x["kept"] for x in tri_valid),
  "disclaimer":"Retrospective final odds, not purchase-time odds; incomplete selection can bias ROI; never report as total HARUQ return."}
(OUT/"audit_summary.json").write_text(json.dumps(ref,ensure_ascii=False,indent=2)+"\n")
print("HARUQ_FINAL_DAY_4X_PARTIAL",json.dumps(ref["odds4_partial"],ensure_ascii=False),flush=True)
con.close()
