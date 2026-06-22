from __future__ import annotations

import uuid
from typing import Any

from cloud_backend import CloudDB


def append_transaction(db: CloudDB, record_type: str, related_batch_id: str | None,
                       actor: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    transaction_id = f"TX-{uuid.uuid4().hex[:12].upper()}"
    result = db.rpc("append_ledger_transaction", {
        "p_transaction_id": transaction_id,
        "p_record_type": record_type,
        "p_related_batch_id": related_batch_id,
        "p_actor_user_id": actor.get("id"),
        "p_actor_individual_id": actor.get("individual_user_id"),
        "p_actor_role": actor.get("role", "system"),
        "p_actor_org": actor.get("organisation", "system"),
        "p_payload": payload,
    })
    if isinstance(result, list) and result:
        return result[0]
    return result if isinstance(result, dict) else {"transaction_id": transaction_id}


def verify_ledger(db: CloudDB) -> dict[str, Any]:
    result = db.rpc("verify_ledger", {})
    if isinstance(result, list) and result:
        result = result[0]
    return result if isinstance(result, dict) else {
        "valid": False, "checked": 0, "message": "Ledger verification returned no result"
    }
