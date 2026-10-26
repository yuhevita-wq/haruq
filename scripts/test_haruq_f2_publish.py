"""Smoke-test web publishing of the sole authorized HaruQ F2 purchase change."""
import copy,json,tempfile
from pathlib import Path
from scripts.haruq_publish_web import export_result
from scripts.haruq_operating_policy import apply_user_policy

base={"exacta":{"label":"HIGH","stake_per_ticket_yen":500,"points":4,
                 "tickets":["5>3","5>7","5>2","5>1"],"total_yen":2000},
      "trifecta":{"label":"S3-HIGH","stake_per_ticket_yen":500,"points":6,
                  "tickets":["5>3>7","5>3>2","5>7>3","5>7>2","5>2>3","5>2>7"],"total_yen":3000}}
confirmed={"status":"confirmed","is_final_day":True,
    "source_url":"https://keirin.netkeiba.com/race/course/?jyo_cd=34",
    "race_id":"202610263409"}
operation=apply_user_policy(base,grade="F2",score_gap=2.1,meeting_day=confirmed)
value={
 "system":"FLAGSHIP_HARUQUBE_20260321_V1",
 "display_name":"ハルキュー",
 "model_sha256":"e70690f4538b77e927a042e7ae2db312f8a0a4f16bf72def37e7ccad3568c193",
 "race_id":"202610263409","date":"2026-10-26","grade":"F2","velodrome":"川崎",
 "race_number":9,"start_time":"23:30","status":"発走前",
 "confidence":2.1,
 "ranked":[{"rank":i,"bike":b,"name":str(b),"score":5-i} for i,b in enumerate([5,3,7,2,1,4,6],1)],
 "s3_policy":operation,"s3_decision":operation["trifecta_decision_ja"],"bets":operation["approved_bets"],
 "total_yen":operation["approved_total_yen"],
 "meeting_day":confirmed,"f2_all_grades_eligible":True
}

def check(payload,accepted):
 with tempfile.TemporaryDirectory() as tmp:
  src=Path(tmp)/"source.json";src.write_text(json.dumps(payload,ensure_ascii=False))
  try:
   export_result(src,Path(tmp)/"web","12999","testsha")
  except ValueError:
   assert not accepted,"Expected accepted publish"
  else:
   assert accepted,"Expected rejected publish"

check(value,True)
wrong=copy.deepcopy(value)
wrong["bets"]["exacta"]["tickets"][0]="5>3"
wrong["s3_policy"]["approved_bets"]["exacta"]["tickets"][0]="5>3"
check(wrong,False)
bad=copy.deepcopy(value)
bad["meeting_day"]["is_final_day"]=False
check(bad,False)
bad2=copy.deepcopy(value)
bad2["confidence"]=1.99
check(bad2,False)
unverified={"status":"unverified","is_final_day":None}
op=apply_user_policy(base,grade="F2",score_gap=3.,meeting_day=unverified)
no_purchase=copy.deepcopy(value)
no_purchase.update(confidence=3.,s3_policy=op,bets=op["approved_bets"],
                   total_yen=0,meeting_day=unverified)
check(no_purchase,True)
print("F2_LIVE_WEB_PUBLISH_CONTRACT_PASSED")
