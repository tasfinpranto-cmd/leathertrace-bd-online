from __future__ import annotations

import hashlib
import math
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_engine import analyse_image_bytes
from cloud_backend import CloudDB
from config import ACCESS_PROFILES, ROLE_CODES, THRESHOLDS
from google_maps import maps_url
from ledger import append_transaction, verify_ledger
from permissions import can, require
from security import hash_password, verify_password
from smart_contract import evaluate


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

def _clean_optional(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def authenticate(db: CloudDB, identity: str, password: str) -> dict[str, Any] | None:
    user = db.select_one("app_users", filters={"individual_user_id": identity, "active": True})
    if not user:
        user = db.select_one("app_users", filters={"username": identity, "active": True})
    success = bool(user and verify_password(password, str(user["password_salt"]), str(user["password_hash"])))
    try:
        db.insert("login_audit", {"identity_entered": identity, "individual_user_id": user.get("individual_user_id") if user else None,
                                  "success": success, "logged_at": utc_now()})
    except Exception:
        pass
    if not success:
        return None
    return {k: user.get(k) for k in ["id","individual_user_id","username","full_name","role","role_code",
                                      "access_profile","organisation","must_change_password"]}


def change_password(db: CloudDB, actor: dict[str, Any], current_password: str, new_password: str) -> None:
    require(actor, "password.change")
    row = db.select_one("app_users", filters={"id": actor["id"]})
    if not row or not verify_password(current_password, row["password_salt"], row["password_hash"]):
        raise ValueError("Current password is incorrect")
    salt, digest = hash_password(new_password)
    db.update("app_users", {"password_salt": salt, "password_hash": digest,
                            "must_change_password": False, "password_changed_at": utc_now()}, filters={"id": actor["id"]})
    append_transaction(db, "PASSWORD_CHANGED", None, actor, {"individual_user_id": actor["individual_user_id"]})


def _region_code(value: str) -> str:
    cleaned = "".join(ch for ch in value.upper() if ch.isalnum())
    return (cleaned[:3] or "GEN").ljust(3, "X")


def create_user(db: CloudDB, actor: dict[str, Any], *, username: str, full_name: str,
                temporary_password: str, role: str, organisation: str, region_code: str) -> dict[str, Any]:
    require(actor, "*")
    if actor.get("role") != "admin":
        raise PermissionError("Only an administrator can create accounts")
    prefix = ROLE_CODES[role]
    region = _region_code(region_code)
    base = f"{prefix}-{region}"
    existing = db.select("app_users", columns="individual_user_id", order="id")
    numbers = []
    for row in existing:
        value = str(row.get("individual_user_id", ""))
        if value.startswith(base + "-"):
            try: numbers.append(int(value.rsplit("-", 1)[1]))
            except Exception: pass
    individual_id = f"{base}-{max(numbers, default=0)+1:04d}"
    salt, digest = hash_password(temporary_password)
    return db.insert("app_users", {
        "individual_user_id": individual_id, "username": username, "full_name": full_name,
        "password_salt": salt, "password_hash": digest, "role": role,
        "role_code": prefix, "access_profile": ACCESS_PROFILES[role], "organisation": organisation,
        "active": True, "must_change_password": True, "created_at": utc_now(),
    })


def set_user_active(db: CloudDB, actor: dict[str, Any], user_id: int, active: bool) -> None:
    if actor.get("role") != "admin": raise PermissionError("Only admin can change account status")
    if int(user_id) == int(actor["id"]) and not active: raise ValueError("You cannot deactivate your own account")
    db.update("app_users", {"active": active}, filters={"id": user_id})


def create_collector_batch(db: CloudDB, actor: dict[str, Any], form: dict[str, Any],
                           image_bytes: bytes, original_name: str, mime_type: str | None,
                           model_path: str | None = None, *, sync_excel: bool = True) -> dict[str, Any]:
    require(actor, "batch.create"); require(actor, "image.upload")
    if not image_bytes: raise ValueError("A leather image is required")
    source_id, batch_id, inspection_id = generate_id("SRC"), generate_id("RHB"), generate_id("INS")
    source = db.insert("source_receipts", {
        "source_receipt_id": source_id, "created_by": actor["id"], "source_type": form["source_type"],
        "source_region": form["source_region"], "reference_status": form["reference_status"],
        "official_reference": form.get("official_reference") or None,
        "gps_lat": form.get("gps_lat"), "gps_lon": form.get("gps_lon"),
        "formatted_address": form.get("formatted_address") or None,
        "google_place_id": form.get("google_place_id") or None,
        "google_maps_url": maps_url(form.get("gps_lat"), form.get("gps_lon")),
        "gps_capture_method": form.get("gps_capture_method", "Manual Correction"),
        "slaughter_point_type": form["slaughter_point_type"],
        "preservation_method": form["preservation_method"],
        "salting_delay_hours": float(form["salting_delay_hours"]),
        "collection_timestamp": form["collection_timestamp"], "notes": form.get("notes") or None,
        "row_version": 1, "created_at": utc_now(), "updated_at": utc_now(), "updated_by": actor["id"],
    })
    batch = db.insert("batches", {
        "batch_id": batch_id, "source_receipt_id": source["id"], "collector_user_id": actor["id"],
        "hide_count": int(form["hide_count"]), "status": "SUBMITTED", "row_version": 1,
        "created_at": utc_now(), "updated_at": utc_now(),
    })
    suffix = Path(original_name).suffix.lower() or ".jpg"
    storage_path = f"collector/{actor['individual_user_id']}/{batch_id}/{inspection_id}{suffix}"
    db.upload_bytes(db.settings.image_bucket, storage_path, image_bytes,
                    mime_type or mimetypes.guess_type(original_name)[0] or "image/jpeg")
    analysis = analyse_image_bytes(image_bytes, model_path)
    image_hash = hashlib.sha256(image_bytes).hexdigest()
    inspection = db.insert("inspections", {
        "inspection_id": inspection_id, "batch_id": batch["id"], "image_storage_path": storage_path,
        "original_filename": original_name, "image_sha256": image_hash, "image_uploaded_by": actor["id"],
        "image_uploaded_at": utc_now(), "ai_mode": analysis["mode"],
        "detected_defects": analysis["detected_defects"], "defect_score": analysis["defect_score"],
        "defective_area_pct": analysis["defective_area_pct"], "usable_area_pct": analysis["usable_area_pct"],
        "ai_suggested_grade": analysis["suggested_grade"], "ai_confidence": analysis["confidence"],
        "status": "AI_GRADED_PENDING_TANNERY", "created_at": utc_now(),
    })
    append_transaction(db, "COLLECTOR_BATCH_SUBMITTED", batch_id, actor, {
        "source_receipt_id": source_id, "source_type": form["source_type"], "source_region": form["source_region"],
        "collection_timestamp": form["collection_timestamp"], "gps_lat": form.get("gps_lat"),
        "gps_lon": form.get("gps_lon"), "hide_count": int(form["hide_count"]),
        "preservation_method": form["preservation_method"], "salting_delay_hours": float(form["salting_delay_hours"]),
    })
    append_transaction(db, "COLLECTOR_IMAGE_UPLOADED", batch_id, actor, {
        "inspection_id": inspection_id, "image_sha256": image_hash, "image_uploaded_at": inspection["image_uploaded_at"],
        "image_storage_reference": storage_path,
    })
    append_transaction(db, "AI_GRADE_GENERATED", batch_id, actor, {
        "inspection_id": inspection_id, "ai_mode": analysis["mode"],
        "detected_defects": analysis["detected_defects"], "defect_score": analysis["defect_score"],
        "ai_suggested_grade": analysis["suggested_grade"], "ai_confidence": analysis["confidence"],
    })
    if sync_excel:
        from excel_sync import sync_master_workbook
        sync_master_workbook(db, actor, f"Collector batch {batch_id} submitted")
    return {"batch_id": batch_id, "inspection_id": inspection_id, **analysis, "storage_path": storage_path}


def create_excel_batch_without_image(db: CloudDB, actor: dict[str, Any], row: dict[str, Any], *, sync_excel: bool = True) -> str:
    require(actor, "excel.source_import")
    source_id, batch_id = generate_id("SRC"), str(row.get("batch_id") or generate_id("RHB"))
    source = db.insert("source_receipts", {
        "source_receipt_id": source_id, "created_by": actor["id"], "source_type": row["source_type"],
        "source_region": row["source_region"], "reference_status": row.get("reference_status") or "Not Available",
        "official_reference": _clean_optional(row.get("official_reference")),
        "gps_lat": _clean_optional(row.get("gps_latitude")),
        "gps_lon": _clean_optional(row.get("gps_longitude")),
        "formatted_address": _clean_optional(row.get("formatted_address")),
        "google_maps_url": maps_url(_clean_optional(row.get("gps_latitude")), _clean_optional(row.get("gps_longitude"))),
        "gps_capture_method": "Excel Import", "slaughter_point_type": row.get("slaughter_point_type") or "Unknown",
        "preservation_method": row["preservation_method"], "salting_delay_hours": float(row["salting_delay_hours"]),
        "collection_timestamp": str(row["collection_timestamp"]), "notes": row.get("notes") or None,
        "row_version": 1, "created_at": utc_now(), "updated_at": utc_now(), "updated_by": actor["id"],
    })
    db.insert("batches", {"batch_id": batch_id, "source_receipt_id": source["id"],
                           "collector_user_id": actor["id"], "hide_count": int(row["hide_count"]),
                           "status": "WAITING_IMAGE", "row_version": 1, "created_at": utc_now(), "updated_at": utc_now()})
    append_transaction(db, "EXCEL_SOURCE_BATCH_IMPORTED", batch_id, actor, {"source_receipt_id": source_id})
    if sync_excel:
        from excel_sync import sync_master_workbook
        sync_master_workbook(db, actor, f"Excel source batch {batch_id} imported")
    return batch_id


def list_batch_view(db: CloudDB, actor: dict[str, Any]) -> list[dict[str, Any]]:
    filters = {"collector_user_id": actor["id"]} if actor["role"] == "collector" else None
    return db.select("source_batch_view", filters=filters, order="id", desc=True)


def attach_image_to_excel_batch(db: CloudDB, actor: dict[str, Any], batch_db_id: int, image_bytes: bytes,
                                original_name: str, mime_type: str | None, model_path: str | None = None) -> dict[str, Any]:
    require(actor, "image.upload")
    batch = db.select_one("batches", filters={"id": batch_db_id, "collector_user_id": actor["id"]})
    if not batch or batch["status"] != "WAITING_IMAGE": raise ValueError("Eligible Excel-imported batch not found")
    inspection_id = generate_id("INS"); suffix = Path(original_name).suffix.lower() or ".jpg"
    path = f"collector/{actor['individual_user_id']}/{batch['batch_id']}/{inspection_id}{suffix}"
    db.upload_bytes(db.settings.image_bucket, path, image_bytes, mime_type or "image/jpeg")
    analysis = analyse_image_bytes(image_bytes, model_path); image_hash = hashlib.sha256(image_bytes).hexdigest()
    db.insert("inspections", {"inspection_id": inspection_id, "batch_id": batch["id"], "image_storage_path": path,
        "original_filename": original_name, "image_sha256": image_hash, "image_uploaded_by": actor["id"],
        "image_uploaded_at": utc_now(), "ai_mode": analysis["mode"], "detected_defects": analysis["detected_defects"],
        "defect_score": analysis["defect_score"], "defective_area_pct": analysis["defective_area_pct"],
        "usable_area_pct": analysis["usable_area_pct"], "ai_suggested_grade": analysis["suggested_grade"],
        "ai_confidence": analysis["confidence"], "status": "AI_GRADED_PENDING_TANNERY", "created_at": utc_now()})
    db.update("batches", {"status": "SUBMITTED", "updated_at": utc_now()}, filters={"id": batch["id"]})
    append_transaction(db, "EXCEL_BATCH_IMAGE_AND_AI_ADDED", batch["batch_id"], actor,
                       {"inspection_id": inspection_id, "image_sha256": image_hash,
                        "ai_suggested_grade": analysis["suggested_grade"], "defect_score": analysis["defect_score"]})
    from excel_sync import sync_master_workbook
    sync_master_workbook(db, actor, f"Image added to Excel batch {batch['batch_id']}")
    return {"batch_id": batch["batch_id"], **analysis}


def tannery_queue(db: CloudDB) -> list[dict[str, Any]]:
    return db.select("tannery_receive_view", order="id", desc=True)


def receive_batch(db: CloudDB, actor: dict[str, Any], batch_db_id: int, received_quantity: int, notes: str) -> str:
    require(actor, "intake.confirm")
    row = db.select_one("tannery_receive_view", filters={"id": batch_db_id})
    if not row or row["status"] != "SUBMITTED": raise ValueError("Submitted batch not found")
    intake_id = generate_id("TIN")
    db.insert("tannery_intakes", {"intake_id": intake_id, "batch_id": batch_db_id,
        "receiving_user_id": actor["id"], "receiving_organisation": actor["organisation"],
        "received_at": utc_now(), "received_quantity": received_quantity, "collector_image_verified": True,
        "ai_grade_seen": row.get("ai_suggested_grade"), "intake_status": "RECEIVED", "notes": notes or None,
        "row_version": 1, "updated_at": utc_now()})
    db.update("batches", {"status": "RECEIVED", "tannery_received_by": actor["id"],
                           "received_at": utc_now(), "updated_at": utc_now()}, filters={"id": batch_db_id})
    db.update("inspections", {"status": "PENDING_HUMAN_REVIEW"}, filters={"batch_id": batch_db_id})
    append_transaction(db, "TANNERY_RECEIPT_CONFIRMED", row["batch_id"], actor, {
        "intake_id": intake_id, "collector_image_sha256": row.get("image_sha256"),
        "collector_upload_time": row.get("image_uploaded_at"), "ai_grade_seen": row.get("ai_suggested_grade"),
        "received_quantity": received_quantity,
    })
    from excel_sync import sync_master_workbook
    sync_master_workbook(db, actor, f"Tannery received {row['batch_id']}")
    return intake_id


def pending_inspections(db: CloudDB) -> list[dict[str, Any]]:
    return db.select("inspection_view", filters={"status": "PENDING_HUMAN_REVIEW"}, order="id")


def confirm_grade(db: CloudDB, actor: dict[str, Any], inspection_db_id: int, grade: str, reason: str | None) -> None:
    require(actor, "grade.confirm")
    row = db.select_one("inspection_view", filters={"id": inspection_db_id})
    if not row: raise ValueError("Inspection not found")
    if grade != row["ai_suggested_grade"]:
        require(actor, "grade.override")
        if not (reason or "").strip(): raise ValueError("Override reason is required")
    db.update("inspections", {"human_confirmed_grade": grade, "override_reason": reason or None,
        "inspector_user_id": actor["id"], "status": "CONFIRMED", "reviewed_at": utc_now()}, filters={"id": inspection_db_id})
    db.update("batches", {"status": "QUALITY_CONFIRMED", "updated_at": utc_now()}, filters={"id": row["batch_id_db"]})
    append_transaction(db, "HUMAN_GRADE_CONFIRMED", row["batch_id"], actor, {
        "inspection_id": row["inspection_id"], "ai_grade": row["ai_suggested_grade"],
        "confirmed_grade": grade, "override_reason": reason,
    })
    from excel_sync import sync_master_workbook
    sync_master_workbook(db, actor, f"Grade confirmed for {row['batch_id']}")


def environmental_status(ph: float, chromium: float, bod: float, cod: float) -> str:
    ok = THRESHOLDS["pH_min"] <= ph <= THRESHOLDS["pH_max"] and chromium <= THRESHOLDS["chromium_limit_mgL"] \
         and bod <= THRESHOLDS["BOD_limit_mgL"] and cod <= THRESHOLDS["COD_limit_mgL"]
    return "PASS" if ok else "FAIL"


def create_environmental_record(db: CloudDB, actor: dict[str, Any], form: dict[str, Any]) -> str:
    require(actor, "environment.create")
    rec_id = generate_id("ENV"); status = environmental_status(float(form["ph"]), float(form["chromium_mgL"]),
                                                                float(form["bod_mgL"]), float(form["cod_mgL"]))
    db.insert("environmental_records", {"effluent_record_id": rec_id, "production_shift_id": form["production_shift_id"],
        "sample_timestamp": form["sample_timestamp"], "measurement_source": form["measurement_source"],
        "ph": form["ph"], "chromium_mgL": form["chromium_mgL"], "bod_mgL": form["bod_mgL"],
        "cod_mgL": form["cod_mgL"], "threshold_version": "BD-POC-v2", "compliance_status": status,
        "entered_by": actor["id"], "created_at": utc_now()})
    append_transaction(db, "ENVIRONMENTAL_RECORD_CREATED", None, actor, {**form, "effluent_record_id": rec_id, "status": status})
    from excel_sync import sync_master_workbook
    sync_master_workbook(db, actor, f"Environmental record {rec_id} added")
    return rec_id


def processing_candidates(db: CloudDB) -> list[dict[str, Any]]:
    return db.select("processing_candidate_view", order="id")


def create_processing_and_decision(db: CloudDB, actor: dict[str, Any], batch_db_id: int,
                                   shift_id: str, environmental_record_id: int | None,
                                   stage: str, start: str, end: str | None, output: float | None) -> dict[str, Any]:
    require(actor, "processing.create"); require(actor, "decision.create")
    candidate = db.select_one("processing_candidate_view", filters={"id": batch_db_id})
    if not candidate: raise ValueError("Eligible batch not found")
    proc_id = generate_id("PLT")
    proc = db.insert("processing_lots", {"processing_lot_id": proc_id, "batch_id": batch_db_id,
        "production_shift_id": shift_id, "environmental_record_id": environmental_record_id,
        "process_stage": stage, "process_start": start, "process_end": end, "output_area_sqft": output,
        "created_by": actor["id"], "created_at": utc_now()})
    env = db.select_one("environmental_records", filters={"id": environmental_record_id}) if environmental_record_id else None
    integrity = verify_ledger(db)
    result = evaluate(salting_delay_hours=float(candidate["salting_delay_hours"]),
        reference_status=str(candidate["reference_status"]), ai_grade=str(candidate["ai_suggested_grade"]),
        human_grade=candidate.get("human_confirmed_grade"), defect_score=float(candidate["defect_score"]),
        environmental_status=env.get("compliance_status") if env else None, ledger_valid=bool(integrity.get("valid")))
    decision_id = generate_id("DEC")
    db.insert("decisions", {"decision_id": decision_id, "batch_id": batch_db_id,
        "final_decision": result["final_decision"], "payment_action": result["payment_action"],
        "quality_status": result["quality_status"], "environmental_status": result["environmental_status"],
        "integrity_status": result["integrity_status"], "reasons": result["reasons"],
        "created_by": actor["id"], "created_at": utc_now()})
    db.update("batches", {"status": "PROCESSING", "updated_at": utc_now()}, filters={"id": batch_db_id})
    append_transaction(db, "PROCESSING_AND_DECISION_CREATED", candidate["batch_id"], actor,
                       {"processing_lot_id": proc_id, "decision_id": decision_id, **result})
    from excel_sync import sync_master_workbook
    sync_master_workbook(db, actor, f"Processing and decision for {candidate['batch_id']}")
    return {"processing_lot_id": proc_id, "decision_id": decision_id, **result}


def create_finished_lot(db: CloudDB, actor: dict[str, Any], processing_lot_db_id: int,
                        market: str, buyer_reference: str | None) -> dict[str, Any]:
    require(actor, "finished_lot.create")
    proc = db.select_one("processing_view", filters={"id": processing_lot_db_id})
    if not proc: raise ValueError("Processing lot not found")
    lot_id, qr_id = generate_id("FLL"), generate_id("TRC")
    db.insert("finished_lots", {"finished_lot_id": lot_id, "processing_lot_id": processing_lot_db_id,
        "traceability_qr_id": qr_id, "destination_market": market, "buyer_reference": buyer_reference,
        "status": "TRACEABLE", "created_by": actor["id"], "created_at": utc_now()})
    db.update("batches", {"status": "FINISHED", "updated_at": utc_now()}, filters={"id": proc["batch_id_db"]})
    append_transaction(db, "FINISHED_LEATHER_LOT_CREATED", proc["batch_id"], actor,
                       {"finished_lot_id": lot_id, "traceability_qr_id": qr_id, "destination_market": market})
    from excel_sync import sync_master_workbook
    sync_master_workbook(db, actor, f"Finished lot {lot_id} created")
    return {"finished_lot_id": lot_id, "traceability_qr_id": qr_id}


def traceability_rows(db: CloudDB) -> list[dict[str, Any]]:
    return db.select("traceability_view", order="id", desc=True)
