from __future__ import annotations

from typing import Final

PERMISSIONS: Final[dict[str, set[str]]] = {
    "collector": {
        "batch.create", "batch.read_own", "batch.edit_own_draft", "image.upload",
        "ai.read_own", "excel.source_import", "excel.download", "password.change",
    },
    "tannery_intake": {
        "batch.read_submitted", "image.read", "ai.read", "gps.read", "intake.confirm",
        "excel.download", "password.change",
    },
    "quality_inspector": {
        "batch.read_received", "image.read", "ai.read", "grade.confirm", "grade.override",
        "excel.download", "password.change",
    },
    "environmental_officer": {
        "environment.create", "environment.read", "excel.environment_import",
        "excel.download", "password.change",
    },
    "tannery_processing": {
        "batch.read_confirmed", "processing.create", "decision.create", "decision.review",
        "finished_lot.create", "excel.download", "password.change",
    },
    "buyer": {
        "traceability.read", "image.read_authorised", "qr.read", "excel.download_summary",
        "password.change",
    },
    "auditor": {
        "ledger.read", "ledger.verify", "audit.read", "traceability.read",
        "excel.download", "password.change",
    },
    "admin": {"*"},
}


def can(actor: dict, permission: str) -> bool:
    granted = PERMISSIONS.get(str(actor.get("role")), set())
    return "*" in granted or permission in granted


def require(actor: dict, permission: str) -> None:
    if not can(actor, permission):
        raise PermissionError(
            f"Access denied: user {actor.get('individual_user_id', actor.get('username'))} "
            f"is not authorised for {permission}."
        )


def permission_summary(role: str) -> str:
    values = sorted(PERMISSIONS.get(role, set()))
    return "; ".join(values)
