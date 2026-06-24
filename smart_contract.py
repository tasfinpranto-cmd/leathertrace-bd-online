```python
from __future__ import annotations

from typing import Any

from config import THRESHOLDS


def build_result(
    *,
    final_decision: str,
    payment_action: str,
    quality_status: str,
    environmental_status: str,
    integrity_status: str,
    reasons: list[str],
) -> dict[str, Any]:
    """Create a consistent smart-decision response."""
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
    """
    Evaluate the sourcing, quality, environmental and ledger conditions
    of a leather batch.

    Decision logic:
    - Invalid ledger -> Integrity Alert
    - Severe preservation delay, Grade C or severe defect -> Rejected
    - Environmental FAIL -> Batch Hold
    - Missing environmental record -> Manual Review
    - AI and human grades differ -> Manual Review
    - Preservation warning exceeded -> Manual Review
    - Grade B with matching AI/human grade -> Conditionally Accepted
    - Grade A with unverified source -> Conditionally Accepted
    - Grade A with all conditions satisfied -> Accepted
    """

    environmental = (
        environmental_status.strip().upper()
        if environmental_status
        else "MISSING"
    )

    integrity = "VERIFIED" if ledger_valid else "FAILED"

    normalized_ai_grade = (ai_grade or "").strip().upper()

    normalized_human_grade = (
        human_grade.strip().upper()
        if human_grade
        else None
    )

    final_grade = normalized_human_grade or normalized_ai_grade

    reference_verified = (
        (reference_status or "").strip().lower() == "verified"
    )

    # 1. Ledger-integrity check
    if not ledger_valid:
        return build_result(
            final_decision="Integrity Alert",
            payment_action="Transaction Frozen",
            quality_status="UNKNOWN",
            environmental_status=environmental,
            integrity_status=integrity,
            reasons=["Ledger verification failed"],
        )

    # 2. Validate the final grade
    if final_grade not in {"A", "B", "C"}:
        return build_result(
            final_decision="Manual Review",
            payment_action="Payment Pending",
            quality_status="UNKNOWN",
            environmental_status=environmental,
            integrity_status=integrity,
            reasons=["A valid final quality grade is not available"],
        )

    quality_status = "PASS"
    rejection_reasons: list[str] = []

    # 3. Severe preservation-delay check
    if (
        salting_delay_hours
        > THRESHOLDS["salting_delay_reject_hours"]
    ):
        quality_status = "FAIL"
        rejection_reasons.append("Severe preservation delay")

    # 4. Severe defect check
    if defect_score >= THRESHOLDS["severe_defect_score"]:
        quality_status = "FAIL"
        rejection_reasons.append("Severe leather defects")

    # 5. Grade C is not eligible for downstream approval
    if final_grade == "C":
        quality_status = "FAIL"
        rejection_reasons.append(
            "Grade C is not eligible for downstream approval"
        )

    if quality_status == "FAIL":
        return build_result(
            final_decision="Rejected",
            payment_action="Payment Not Authorised",
            quality_status=quality_status,
            environmental_status=environmental,
            integrity_status=integrity,
            reasons=rejection_reasons,
        )

    # 6. Environmental-compliance check
    if environmental == "FAIL":
        return build_result(
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
        return build_result(
            final_decision="Manual Review",
            payment_action="Payment Pending",
            quality_status=quality_status,
            environmental_status=environmental,
            integrity_status=integrity,
            reasons=[
                "Environmental monitoring record is not linked"
            ],
        )

    # 7. AI and human grades must agree
    if (
        normalized_human_grade
        and normalized_ai_grade != normalized_human_grade
    ):
        return build_result(
            final_decision="Manual Review",
            payment_action="Payment Pending",
            quality_status=quality_status,
            environmental_status=environmental,
            integrity_status=integrity,
            reasons=["AI and human grades differ"],
        )

    # 8. Preservation-warning check
    if (
        salting_delay_hours
        > THRESHOLDS["salting_delay_warning_hours"]
    ):
        return build_result(
            final_decision="Manual Review",
            payment_action="Payment Pending",
            quality_status=quality_status,
            environmental_status=environmental,
            integrity_status=integrity,
            reasons=["Preservation delay exceeded warning limit"],
        )

    # 9. Grade B receives conditional approval
    if final_grade == "B":
        conditional_reasons = [
            "Grade B accepted under conditional approval"
        ]

        if not reference_verified:
            conditional_reasons.append(
                "Official source reference is not verified"
            )

        return build_result(
            final_decision="Conditionally Accepted",
            payment_action="Manual Approval Required",
            quality_status=quality_status,
            environmental_status=environmental,
            integrity_status=integrity,
            reasons=conditional_reasons,
        )

    # 10. Grade A with an unverified source receives conditional approval
    if not reference_verified:
        return build_result(
            final_decision="Conditionally Accepted",
            payment_action="Manual Approval Required",
            quality_status=quality_status,
            environmental_status=environmental,
            integrity_status=integrity,
            reasons=[
                "Official source reference is not verified"
            ],
        )

    # 11. All configured conditions are satisfied
    return build_result(
        final_decision="Accepted",
        payment_action="Payment Authorised",
        quality_status=quality_status,
        environmental_status=environmental,
        integrity_status=integrity,
        reasons=["All configured conditions were met"],
    )
```
