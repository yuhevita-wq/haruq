"""User-authorized HaruQ purchase V4 on unchanged March 21 prediction model.

F2: ONLY confirmed meeting-final-day, score gap >= 2.00, exacta rank
1 -> ranks 3 and 4, 500 yen each, never buy F2 trifecta.
Other grades: preserve V3 purchases identically. Neither rankings,
features nor model files may be changed.
"""
DISPLAY_NAME = "ハルキュー"
POLICY_VERSION = "HARUQ_F2_FINALDAY_EXACTA_1_TO_3_4_GAP2_V4_20261026"


def apply_user_policy(
    original_bets: dict, *, grade: str | None = None,
    score_gap: float | None = None, meeting_day: dict | None = None,
) -> dict:
    exacta = original_bets["exacta"]
    trifecta = original_bets["trifecta"]
    ex_tier = exacta["label"]
    tier = trifecta["label"]
    assert ex_tier in {"HIGH", "MED+", "MED", "LOW", "SKIP"}
    assert tier in {"S3-HIGH", "S3-MED+", "S3-MED", "LOW", "SKIP"}

    if grade == "F2":
        if score_gap is None:
            raise ValueError("F2 special policy needs the actual frozen model score gap")
        day = meeting_day or {}
        is_final = day.get("is_final_day") is True and day.get("status") == "confirmed"
        # In the archived fixed policy, both tiers must be HIGH at gap >= 2.0.
        # The candidate tickets are the SECOND and THIRD original exacta slots:
        # model-rank 1 -> model-rank 3 / model-rank 4.
        qualifies = score_gap >= 2.0 and is_final
        if qualifies:
            assert ex_tier == "HIGH" and tier == "S3-HIGH"
            assert exacta["points"] == 4 and len(set(exacta["tickets"])) == 4
            assert exacta["stake_per_ticket_yen"] == 500
            picks = list(exacta["tickets"][1:3])
            assert len(picks) == 2 and len(set(picks)) == 2
            approved_exacta = {
                **exacta, "tickets": picks, "points": 2,
                "stake_per_ticket_yen": 500, "total_yen": 1000,
                "decision": "BUY", "decision_ja": "買う（F2最終日専用2点）",
            }
        else:
            reason = ("最終日未確認" if day.get("is_final_day") is None
                      else "最終日以外" if not is_final else "スコア差2.0未満")
            approved_exacta = {
                "label": ex_tier, "stake_per_ticket_yen": 0,
                "points": 0, "tickets": [], "total_yen": 0,
                "decision": "REJECT", "decision_ja": "買わない（F2：" + reason + "）",
            }
        approved_tri = {
            "label": tier, "decision": "REJECT",
            "decision_ja": "買わない（F2専用ルール：3連単なし）",
            "tickets": [], "points": 0,
            "stake_per_ticket_yen": 0, "total_yen": 0,
        }
        return {
            "name": DISPLAY_NAME,
            "policy_version": POLICY_VERSION,
            "trifecta_tier": tier,
            "trifecta_decision": "REJECT",
            "trifecta_decision_ja": approved_tri["decision_ja"],
            "approved_bets": {"exacta": approved_exacta, "trifecta": approved_tri},
            "under_review": {"trifecta": {
                "label": tier, "tickets": [], "points": 0,
                "stake_per_ticket_yen": 0, "conditional_total_yen": 0,
                "counts_as_purchase": False, "decision": "なし（F2の3連単は購入対象外）",
            }},
            "approved_total_yen": approved_exacta["total_yen"],
            "never_modify_model": True,
            "user_review_required_for_med": False,
            "exacta_high_only": True, "trifecta_high_only": True,
            "f2_eligible": True,
            "f2_final_day_policy": True,
            "f2_meeting_day_proof_status": day.get("status", "unverified"),
            "f2_score_gap_threshold": 2.0,
            "f2_buying_formation": "rank1>rank3;rank1>rank4",
        }

    if ex_tier == "HIGH":
        assert exacta["points"] == 4 and len(set(exacta["tickets"])) == 4
        assert exacta["stake_per_ticket_yen"] == 500
        assert exacta["total_yen"] == 2000
        approved_exacta = {**exacta, "tickets":list(exacta["tickets"]), "decision":"BUY", "decision_ja":"買う"}
    else:
        approved_exacta = {
            "label":ex_tier,
            "stake_per_ticket_yen":0,"points":0,"tickets":[],"total_yen":0,
            "decision":"REJECT","decision_ja":"買わない（HIGH未満）",
        }

    if tier == "S3-HIGH":
        assert trifecta["points"] == 6 and len(set(trifecta["tickets"])) == 6
        assert trifecta["stake_per_ticket_yen"] == 500
        assert trifecta["total_yen"] == 3000
        approved_tri = {**trifecta, "tickets":list(trifecta["tickets"]),
                        "decision":"BUY","decision_ja":"必ず買う"}
        decision = "BUY"
        label = "必ず買う"
    else:
        approved_tri = {
            "label":tier,
            "decision":"REJECT",
            "decision_ja":"買わない（S3-HIGH未満）",
            "tickets":[],"points":0,"stake_per_ticket_yen":0,"total_yen":0,
        }
        decision = "REJECT"
        label = "買わない（S3-HIGH未満）"

    # Compatibility: the website must never treat lower confidence as review/buy.
    under_review = {
        "trifecta":{
            "label":tier,"tickets":[],"points":0,"stake_per_ticket_yen":0,
            "conditional_total_yen":0,"counts_as_purchase":False,
            "decision":"なし（MEDも購入対象外）",
        }
    }
    return {
        "name":DISPLAY_NAME,
        "policy_version":POLICY_VERSION,
        "trifecta_tier":tier,
        "trifecta_decision":decision,
        "trifecta_decision_ja":label,
        "approved_bets":{"exacta":approved_exacta,"trifecta":approved_tri},
        "under_review":under_review,
        "approved_total_yen":approved_exacta["total_yen"]+approved_tri["total_yen"],
        "never_modify_model":True,
        "user_review_required_for_med":False,
        "exacta_high_only":True,
        "trifecta_high_only":True,
        "f2_eligible":True,
    }
