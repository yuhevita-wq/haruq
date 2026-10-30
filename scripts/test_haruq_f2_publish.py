"""Smoke-test web publishing of authorized HaruQ F1 and F2 purchases."""
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

# User approved F1 confirmed final day, gap >=1.5, only first two exacta.
for gap in (1.5,1.9999,2.0,2.4):
    f1_base=copy.deepcopy(base)
    if gap<2:
        f1_base["trifecta"].update(label="S3-MED",tickets=[],points=0,
                                    stake_per_ticket_yen=200,total_yen=0)
    p=apply_user_policy(f1_base,grade="F1",score_gap=gap,meeting_day=confirmed)
    data=copy.deepcopy(value)
    data.update(grade="F1",confidence=gap,s3_policy=p,bets=p["approved_bets"],
                s3_decision=p["trifecta_decision_ja"],total_yen=p["approved_total_yen"])
    check(data,True)
    assert data["bets"]["exacta"]["tickets"]==["5>3","5>7"]
    assert data["bets"]["trifecta"]["points"]==(6 if gap>=2 else 0)
    corrupt=copy.deepcopy(data)
    corrupt["bets"]["exacta"]["tickets"][1]="5>2"
    corrupt["s3_policy"]["approved_bets"]["exacta"]["tickets"][1]="5>2"
    check(corrupt,False)
    if gap>=2:
        corrupt_tri=copy.deepcopy(data)
        corrupt_tri["bets"]["trifecta"]["tickets"][0]="5>7>3"
        corrupt_tri["s3_policy"]["approved_bets"]["trifecta"]["tickets"][0]="5>7>3"
        check(corrupt_tri,False)
    bad_date=copy.deepcopy(data)
    bad_date["meeting_day"]["is_final_day"]=False
    check(bad_date,False)

for score in (1.49,2.01):
    for date_meta in ({"status":"confirmed","is_final_day":False},
                      {"status":"unverified","is_final_day":None}):
        f1_base=copy.deepcopy(base)
        if score<2:
            f1_base["trifecta"].update(label="S3-MED",tickets=[],points=0,
                                        stake_per_ticket_yen=200,total_yen=0)
        p=apply_user_policy(f1_base,grade="F1",score_gap=score,meeting_day=date_meta)
        assert p["approved_total_yen"]==0
        data=copy.deepcopy(value)
        data.update(grade="F1",confidence=score,s3_policy=p,bets=p["approved_bets"],
                    s3_decision=p["trifecta_decision_ja"],total_yen=0,meeting_day=date_meta)
        check(data,True)

print("F1_LIVE_WEB_PUBLISH_CONTRACT_PASSED")

# Manual H1 candidates are recomputed at publication; mutated sets must stop.
from scripts.haruq_formation import automatic_formation
new=copy.deepcopy(value)
new.update(grade='F1',meeting_day=confirmed,confidence=2.1)
op=apply_user_policy(copy.deepcopy(base),grade='F1',score_gap=2.1,meeting_day=confirmed)
new.update(s3_policy=op,bets=op['approved_bets'],total_yen=op['approved_total_yen'])
new['line_formation']=[[5,3,7],[2,1],[4,6]]
new['formation_strategy']=automatic_formation(new['ranked'],new['line_formation'],eligible=True)
check(new,True)
corrupt=copy.deepcopy(new)
corrupt['formation_strategy']['selected']['tickets'][0]='9>8>7'
check(corrupt,False)
print('HARUQ_MANUAL_FORMATION_PUBLISH_CONTRACT_PASSED')
