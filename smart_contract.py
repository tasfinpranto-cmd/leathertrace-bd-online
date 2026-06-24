from __future__ import annotations

from typing import Any

from config import THRESHOLDS


def _result(
    *,
    final_decision: str,
    payment_action: str,
    quality_status: str,
    environmental_status: str,
    integrity_status: str,
    reasons: list[str],
) -> dict[str, Any]:
    return {
        "final_decision": final_decision,
        "payment_action": payment_action,
        "quality_status": quality_status,
        "environmental_status": environmental_status,
        "integrity_status": integrity_status,
        "reasons": reasons,
    }


def evaluate(
    *,
    salting_delay_hours: float,
    reference_status: str,
    ai_grade: str,
    human_grade: str | None,
    defect_score: float,
    environmental_status: str | None,
    ledger_valid: bool,
) -> dict[str, Any]:
    environmental = (environmental_status or "MISSING").strip().upper()
    integrity = "VERIFIED" if ledger_valid else "FAILED"

    normalized_ai_grade = (ai_grade or "").strip().upper()
    normalized_human_grade = (
        human_grade.strip().upper() if human_grade else None
    )
    final_grade = normalized_human_grade or normalized_ai_grade

    reference_verified = (
        (reference_status or "").strip().lower() == "verified"
    )

    if not ledger_valid:
        return _result(
            final_decision="Integrity Alert",
            payment_action="Transaction Frozen",
            quality_status="UNKNOWN",
            environmental_status=environmental,
            integrity_status=integrity,
            reasons=["Ledger verification failed"],
        )

    if final_grade not in {"A", "B", "C"}:
        return _result(
            final_decision="Manual Review",
            payment_action="Payment Pending",
            quality_status="UNKNOWN",
            environmental_status=environmental,
            integrity_status=integrity,
            reasons=["A valid final quality grade is not available"],
        )

    if salting_delay_hours > THRESHOLDS["salting_delay_reject_hours"]:
        return _result(
            final_decision="Rejected",
            payment_action="Payment Not Authorised",
            quality_status="FAIL",
            environmental_status=environmental,
            integrity_status=integrity,
            reasons=["Severe preservation delay"],
        )

    if defect_score >= THRESHOLDS["severe_defect_score"]:
        return _result(
            final_decision="Rejected",
            payment_action="Payment Not Authorised",
            quality_status="FAIL",
            environmental_status=environmental,
            integrity_status=integrity,
            reasons=["Severe leather defects"],
        )

    if final_grade == "C":
        return _result(
            final_decision="Rejected",
            payment_action="Payment Not Authorised",
            quality_status="FAIL",
            environmental_status=environmental,
            integrity_status=integrity,
            reasons=["Grade C is not eligible for downstream approval"],
        )

    quality_status = "PASS"

    if environmental == "FAIL":
        return _result(
            final_decision="Batch Hold",
            payment_action="Payment Held",
            quality_status=quality_status,
            environmental_status=environmental,
            integrity_status=integrity,
            reasons=[
                "Production-shift environmental record is non-compliant"
            ],
        )

    if environmental == "MISSING":
        return _result(
            final_decision="Manual Review",
            payment_action="Payment Pending",
            quality_status=quality_status,
            environmental_status=environmental,
            integrity_status=integrity,
            reasons=["Environmental monitoring record is not linked"],
        )

    if (
        normalized_human_grade is not None
        and normalized_human_grade != normalized_ai_grade
    ):
        return _result(
            final_decision="Manual Review",
            payment_action="Payment Pending",
            quality_status=quality_status,
            environmental_status=environmental,
            integrity_status=integrity,
            reasons=["AI and human grades differ"],
        )

    if salting_delay_hours > THRESHOLDS["salting_delay_warning_hours"]:
        return _result(
            final_decision="Manual Review",
            payment_action="Payment Pending",
            quality_status=quality_status,
            environmental_status=environmental,
            integrity_status=integrity,
            reasons=["Preservation delay exceeded warning limit"],
        )

    if final_grade == "B":
        reasons = ["Grade B accepted under conditional approval"]

        if not reference_verified:
            reasons.append("Official source reference is not verified")

        return _result(
            final_decision="Conditionally Accepted",
            payment_action="Manual Approval Required",
            quality_status=quality_status,
            environmental_status=environmental,
            integrity_status=integrity,
            reasons=reasons,
        )

    if not reference_verified:
        return _result(
            final_decision="Conditionally Accepted",
            payment_action="Manual Approval Required",
            quality_status=quality_status,
            environmental_status=environmental,
            integrity_status=integrity,
            reasons=["Official source reference is not verified"],
        )

    return _result(
        final_decision="Accepted",
        payment_action="Payment Authorised",
        quality_status=quality_status,
        environmental_status=environmental,
        integrity_status=integrity,
        reasons=["All configured conditions were met"],
    )
