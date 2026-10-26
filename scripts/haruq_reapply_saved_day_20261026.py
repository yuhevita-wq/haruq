#!/usr/bin/env python3
"""Reapply the approved V5 BUY policy to 2026-10-26 pre-race frozen scores.

This is a TODAY-only publication action, not model training or inference.
The original per-run race artifacts remain immutable.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

import pandas as pd
from config import VELODROME_CODES
from data.scraper import KeirinScraper
from scripts.flagship_live_predict import MODEL_SHA256, strict_tickets
from scripts.haruq_meeting_final_day import resolve_meeting_day
from scripts.haruq_operating_policy import apply_user_policy, POLICY_VERSION
from scripts.haruq_publish_web import export_result

ROOT=Path(__file__).resolve().parent.parent
DAY="2026-10-26"
DAYCOMPACT="20261026"
FROM_RUN=40208399912
OLD_POLICY="HARUQ_HIGH_ONLY_ALL_MARKETS_F2_ELIGIBLE_V3"


def validate_saved_prediction(p):
    rid=p["race_id"]
    if (p["date"]!=DAY or not rid.startswith(DAYCOMPACT)
            or p["system"]!="FLAGSHIP_HARUQUBE_20260321_V1"
            or p["model_sha256"]!=MODEL_SHA256):
        raise RuntimeError("Historical frozen prediction identity mismatch: "+rid)
    if p["s3_policy"]["policy_version"]!=OLD_POLICY:
        raise RuntimeError("Expected immutable pre-V5 baseline snapshot: "+rid)
    before=p["web_record"]
    if before["source_run_id"]!=FROM_RUN:
        raise RuntimeError("Source run was not the verified 2026-10-25 snapshot: "+rid)
    # All original predictions must have been published before racing started.
    saved=datetime.fromisoformat(before["created_at"].replace("Z","+00:00"))
    if saved.date()>=datetime(2026,10,26,tzinfo=timezone.utc).date():
        raise RuntimeError("Not a verified pre-race snapshot: "+rid)
    ranks=p["ranked"]
    if len(ranks)<5 or len({int(r["bike"]) for r in ranks})!=len(ranks):
        raise RuntimeError("Corrupted original prediction ranks: "+rid)
    score=float(p["confidence"])
    if score<0:
        raise RuntimeError("Unexpected negative frozen score gap")
    raw=strict_tickets(pd.DataFrame({"bike_number":[int(x["bike"]) for x in ranks]}),
                       score,p["grade"],allow_f2=True)
    original_bets=p["bets"]
    for market in ("exacta","trifecta"):
        old=original_bets[market]; candidate=raw[market]
        if old["label"]!=candidate["label"]:
            raise RuntimeError("Original frozen model purchase-tier mismatch for "+rid+" "+market)
        original_high=old["label"] in ("HIGH","S3-HIGH")
        expected=candidate["tickets"] if original_high else []
        if old["tickets"]!=expected:
            raise RuntimeError("Original frozen ticket set does not match scores: "+rid)
        if old["total_yen"]!=(500*len(expected)):
            raise RuntimeError("Original fixed 500 yen purchase mismatch: "+rid)
    if p["total_yen"]!=sum(x["total_yen"] for x in original_bets.values()):
        raise RuntimeError("Original pre-V5 total mismatch: "+rid)
    return raw


def main():
    run=os.environ.get("GITHUB_RUN_ID")
    sha=os.environ.get("GITHUB_SHA")
    if not run or not run.isdigit() or not sha:
        raise RuntimeError("Explicit GitHub Actions audited execution required")
    source=ROOT/"docs"/"haruq"/"days"/(DAYCOMPACT+".json")
    old=json.loads(source.read_text(encoding="utf-8"))
    if (old["date"]!=DAY or old["run_id"]!=str(FROM_RUN)
            or old["complete"] is not True or old["total_races"]!=72
            or old["counts"]!={"predicted":66,"excluded":6,"error":0}):
        raise RuntimeError("Day source not the unmodified pre-race archive")
    rows=old["records"]
    if len(rows)!=72 or len({x["race_id"] for x in rows})!=72:
        raise RuntimeError("Duplicate/missing source races")
    scraper=KeirinScraper()
    outputs=[]
    proof_counts={}
    for item in rows:
        if item["status"]!="predicted":
            outputs.append(item)
            continue
        p=item["prediction"]
        if p["race_id"]!=item["race_id"]:
            raise RuntimeError("Daily manifest mismatch")
        raw=validate_saved_prediction(p)
        rid=p["race_id"]
        # Ensure main currently points to this exact frozen snapshot.
        existing=ROOT/"docs"/"haruq"/"results"/(rid+".json")
        current=json.loads(existing.read_text(encoding="utf-8"))
        if (current.get("web_record",{}).get("source_run_id")!=FROM_RUN
                or current["ranked"]!=p["ranked"]
                or current["confidence"]!=p["confidence"]):
            raise RuntimeError("A newer or divergent prediction must not be overwritten: "+rid)
        grade=p["grade"]
        day=(resolve_meeting_day(scraper,rid) if grade in ("F1","F2") else
             {"status":"not_applicable","is_final_day":None,
              "reason":"G_grade_original_purchase_policy","race_id":rid})
        proof_counts[(grade,day["status"],str(day["is_final_day"]))]=(
            proof_counts.get((grade,day["status"],str(day["is_final_day"])),0)+1)
        op=apply_user_policy(raw,grade=grade,score_gap=float(p["confidence"]),meeting_day=day)
        q=dict(p)
        # Only operational fields are changed; frozen model ranks/scores untouched.
        q.update(
            bets=op["approved_bets"],
            total_yen=op["approved_total_yen"],
            s3_policy=op,
            s3_decision=op["trifecta_decision_ja"],
            med_under_review=op["under_review"]["trifecta"],
            meeting_day=day,
            policy_replay={
                "method":"policy-only replay of pre-race 2026-10-26 frozen inference",
                "original_source_run_id":FROM_RUN,
                "original_policy_version":OLD_POLICY,
                "approved_policy_version":POLICY_VERSION,
                "raw_model_scores_recomputed":False,
                "prior_web_record":p["web_record"],
            },
        )
        outputs.append({**item,"prediction":q})
    purchases=[r for r in outputs if r.get("prediction",{}).get("total_yen",0)>0]
    # No file mutation before every input, programme and output has been validated.
    public=ROOT/"docs"/"haruq"/"results"
    from copy import deepcopy
    for item in outputs:
        if item["status"]!="predicted":
            continue
        q=deepcopy(item["prediction"])
        rid=q["race_id"]
        with tempfile.TemporaryDirectory() as td:
            input_path=Path(td)/"output.json"
            input_path.write_text(json.dumps(q,ensure_ascii=False),encoding="utf-8")
            export_result(input_path,public,run,sha)
        item["prediction"]=json.loads((public/(rid+".json")).read_text(encoding="utf-8"))
    total=sum(r["prediction"]["total_yen"] for r in purchases)
    new={**old, "created_at":datetime.now(timezone.utc).isoformat(),
         "run_id":run,"source_commit":sha, "records":outputs,
         "policy_replay":{
             "type":"pre-race-frozen-model-predictions_replayed_with_approved_purchase_policy",
             "original_source_run_id":FROM_RUN,
             "policy_version":POLICY_VERSION,
             "no_model_predictions_rerun":True,
             "original_race_snapshot_archives_unchanged":True,
             "totals":{"races":len(rows),"predicted":66,"excluded":6,
                       "purchase_races":len(purchases),"stake_yen":total},
             "date_proof_counts":[dict(grade=g,status=s,final_day=f,count=n)
                                  for (g,s,f),n in sorted(proof_counts.items())]
         }}
    source.write_text(json.dumps(new,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    report=dict(day=DAY,model_sha256=MODEL_SHA256,policy_version=POLICY_VERSION,
       original_source_run_id=FROM_RUN,run_id=run,venue_count=len(old["venues"]),
       races=len(rows),predicted=66,excluded=6,buying=len(purchases),
       total_stake_yen=total,
       date_proof_counts=new["policy_replay"]["date_proof_counts"],
       purchases=[dict(race_id=r["race_id"],venue=r["velodrome"],
                       race=r["race_number"],start_time=r["start_time"],
                       grade=r["grade"],confidence=r["prediction"]["confidence"],
                       bets=r["prediction"]["bets"],total_yen=r["prediction"]["total_yen"],
                       meeting_day=r["prediction"]["meeting_day"]["meeting_day_label"])
                  for r in purchases])
    target=ROOT/"flagship_daily_results"
    target.mkdir(exist_ok=True)
    (target/"20261026_v5_replay_summary.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("HARUQ_V5_TODAY_REPORT "+json.dumps(report,ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
