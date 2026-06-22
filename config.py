from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

APP_NAME: Final = "AI-Blockchain LeatherTrace-BD Online"
APP_SUBTITLE: Final = (
    "Collector image capture, automatic AI grading, role-based access, Excel sync, "
    "Google Maps location and tamper-evident traceability"
)
IMAGE_BUCKET: Final = "leather-images"
SYSTEM_BUCKET: Final = "system-files"
MASTER_WORKBOOK_PATH: Final = "master/LeatherTrace_BD_Master.xlsx"

THRESHOLDS: Final = {
    "salting_delay_warning_hours": 48.0,
    "salting_delay_reject_hours": 72.0,
    "pH_min": 6.0,
    "pH_max": 9.0,
    "chromium_limit_mgL": 2.0,
    "BOD_limit_mgL": 50.0,
    "COD_limit_mgL": 200.0,
    "severe_defect_score": 0.65,
}

ROLES: Final = {
    "collector": "Collector / Aggregator",
    "tannery_intake": "Tannery Intake Officer",
    "quality_inspector": "Quality Inspector",
    "environmental_officer": "Environmental Officer",
    "tannery_processing": "Tannery Processing Officer",
    "buyer": "Buyer / Exporter",
    "auditor": "Auditor / Compliance Team",
    "admin": "System Administrator",
}

ROLE_CODES: Final = {
    "collector": "CLT",
    "tannery_intake": "TAN-INT",
    "quality_inspector": "TAN-QA",
    "environmental_officer": "TAN-ENV",
    "tannery_processing": "TAN-PRC",
    "buyer": "BUY",
    "auditor": "AUD",
    "admin": "ADM",
}

ACCESS_PROFILES: Final = {
    "collector": "COLLECTOR_STANDARD",
    "tannery_intake": "TANNERY_INTAKE",
    "quality_inspector": "QUALITY_CONTROL",
    "environmental_officer": "ENVIRONMENTAL_DATA",
    "tannery_processing": "PROCESSING_CONTROL",
    "buyer": "BUYER_READ_ONLY",
    "auditor": "AUDITOR_READ_ONLY",
    "admin": "SYSTEM_ADMIN",
}

DEMO_ACCOUNTS: Final = {
    "CLT-DHK-0001": "Collector123!",
    "TAN-INT-0001": "Tannery123!",
    "TAN-QA-0001": "Quality123!",
    "TAN-ENV-0001": "Environment123!",
    "TAN-PRC-0001": "Process123!",
    "BUY-EXP-0001": "Buyer123!",
    "AUD-REG-0001": "Audit123!",
    "ADM-SYS-0001": "Admin123!",
}


@dataclass(frozen=True)
class CloudSettings:
    supabase_url: str
    supabase_key: str
    image_bucket: str
    system_bucket: str
    public_url: str
    google_maps_api_key: str


def load_settings(secrets: object | None = None) -> CloudSettings:
    def get(name: str, default: str = "") -> str:
        if secrets is not None:
            try:
                value = secrets.get(name, default)  # type: ignore[attr-defined]
                if value:
                    return str(value)
            except Exception:
                pass
        return os.getenv(name, default)

    return CloudSettings(
        supabase_url=get("SUPABASE_URL"),
        supabase_key=get("SUPABASE_KEY"),
        image_bucket=get("IMAGE_BUCKET", IMAGE_BUCKET),
        system_bucket=get("SYSTEM_BUCKET", SYSTEM_BUCKET),
        public_url=get("APP_PUBLIC_URL", "http://localhost:8501").rstrip("/"),
        google_maps_api_key=get("GOOGLE_MAPS_API_KEY"),
    )
