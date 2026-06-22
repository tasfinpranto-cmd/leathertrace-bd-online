from __future__ import annotations

from typing import Any

from config import THRESHOLDS


def evaluate(*, salting_delay_hours: float, reference_status: str, ai_grade: str,
             human_grade: str | None, defect_score: float,
             environmental_status: str | None, ledger_valid: bool) -> dict[str, Any]:
    reasons: list[str] = []
    environmental = environmental_status or "MISSING"
    integrity = "VERIFIED" if ledger_valid else "FAILED"
    if not ledger_valid:
        return {"final_decision": "Integrity Alert", "payment_action": "Transaction Frozen",
                "quality_status": "UNKNOWN", "environmental_status": environmental,
                "integrity_status": integrity, "reasons": ["Ledger verification failed"]}
    quality_status = "PASS"
    if salting_delay_hours > THRESHOLDS["salting_delay_reject_hours"]:
        quality_status = "FAIL"; reasons.append("Severe preservation delay")
    final_grade = human_grade or ai_grade
    if final_grade == "C" and defect_score >= THRESHOLDS["severe_defect_score"]:
        quality_status = "FAIL"; reasons.append("Severe leather defects")
    if quality_status == "FAIL":
        return {"final_decision": "Rejected", "payment_action": "Payment Not Authorised",
                "quality_status": quality_status, "environmental_status": environmental,
                "integrity_status": integrity, "reasons": reasons}
    if environmental == "FAIL":
        return {"final_decision": "Batch Hold", "payment_action": "Payment Held",
                "quality_status": quality_status, "environmental_status": environmental,
                "integrity_status": integrity,
                "reasons": ["Production-shift environmental record is non-compliant"]}
    if environmental == "MISSING":
        return {"final_decision": "Manual Review", "payment_action": "Payment Pending",
                "quality_status": quality_status, "environmental_status": environmental,
                "integrity_status": integrity,
                "reasons": ["Environmental monitoring record is not linked"]}
    if human_grade and ai_grade != human_grade:
        reasons.append("AI and human grades differ")
    if final_grade == "B":
        reasons.append("Grade B requires review")
    if salting_delay_hours > THRESHOLDS["salting_delay_warning_hours"]:
        reasons.append("Preservation delay exceeded 48 hours")
    if reasons:
        return {"final_decision": "Manual Review", "payment_action": "Payment Pending",
                "quality_status": quality_status, "environmental_status": environmental,
                "integrity_status": integrity, "reasons": reasons}
    if reference_status != "Verified":
        return {"final_decision": "Conditionally Accepted", "payment_action": "Manual Approval Required",
                "quality_status": quality_status, "environmental_status": environmental,
                "integrity_status": integrity,
                "reasons": ["Official source reference is not verified"]}
    return {"final_decision": "Accepted", "payment_action": "Payment Authorised",
            "quality_status": quality_status, "environmental_status": environmental,
            "integrity_status": integrity, "reasons": ["All configured conditions were met"]}
