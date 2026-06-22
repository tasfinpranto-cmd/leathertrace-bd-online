from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps


def _grade(score: float) -> str:
    if score < 0.25:
        return "A"
    if score < 0.50:
        return "B"
    return "C"


def analyse_image_bytes(image_bytes: bytes, model_path: str | None = None) -> dict[str, Any]:
    """Use a custom YOLO model when available; otherwise run a transparent demo heuristic."""
    if model_path and Path(model_path).exists():
        try:
            from ultralytics import YOLO  # optional dependency
            model = YOLO(model_path)
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            results = model.predict(image, verbose=False)
            result = results[0]
            defects: list[dict[str, Any]] = []
            confidences: list[float] = []
            annotated = result.plot()
            if getattr(result, "boxes", None) is not None:
                for cls, conf in zip(result.boxes.cls.tolist(), result.boxes.conf.tolist()):
                    label = result.names[int(cls)]
                    defects.append({"type": label, "confidence": round(float(conf), 3)})
                    confidences.append(float(conf))
            score = min(1.0, (len(defects) * 0.12) + (sum(confidences) / max(1, len(confidences))) * 0.45)
            return {
                "mode": "CUSTOM_YOLO_MODEL",
                "detected_defects": defects or [{"type": "no_major_visible_defect", "confidence": 0.7}],
                "defect_score": round(score, 4),
                "defective_area_pct": round(min(80.0, score * 60), 2),
                "usable_area_pct": round(max(20.0, 100.0 - score * 60), 2),
                "suggested_grade": _grade(score),
                "confidence": round(max(confidences) if confidences else 0.7, 3),
                "annotated_image": annotated,
                "notice": "Custom model inference was used. Accuracy depends on the training dataset and validation.",
            }
        except Exception:
            pass

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        raise ValueError("The uploaded image could not be read") from exc

    image.thumbnail((900, 900))
    gray = ImageOps.grayscale(image)
    arr = np.asarray(gray, dtype=np.float32) / 255.0
    edges = np.asarray(gray.filter(ImageFilter.FIND_EDGES), dtype=np.float32) / 255.0
    edge_ratio = float(np.mean(edges > 0.22))
    p18 = float(np.percentile(arr, 18))
    dark_ratio = float(np.mean(arr <= p18))
    brightness_std = float(np.std(arr))
    rgb = np.asarray(image, dtype=np.float32) / 255.0
    channel_spread = float(np.mean(np.max(rgb, axis=2) - np.min(rgb, axis=2)))
    score = min(1.0, 0.36 * min(edge_ratio * 3.2, 1.0) + 0.22 * min(dark_ratio * 3.0, 1.0)
                + 0.24 * min(brightness_std * 4.0, 1.0) + 0.18 * min(channel_spread * 3.0, 1.0))
    defective_area = round(min(70.0, score * 58.0), 2)
    confidence = round(0.56 + min(0.33, abs(score - 0.38) * 0.72), 3)
    defects: list[dict[str, Any]] = []
    if dark_ratio > 0.18:
        defects.append({"type": "dark_spot", "confidence": round(min(0.94, 0.55 + dark_ratio), 3)})
    if edge_ratio > 0.10:
        defects.append({"type": "cut_or_edge_irregularity", "confidence": round(min(0.93, 0.50 + edge_ratio * 2.0), 3)})
    if brightness_std > 0.19:
        defects.append({"type": "surface_irregularity", "confidence": round(min(0.91, 0.52 + brightness_std), 3)})
    if channel_spread > 0.20:
        defects.append({"type": "colour_or_stain_variation", "confidence": round(min(0.90, 0.50 + channel_spread), 3)})
    if not defects:
        defects.append({"type": "no_major_visible_defect", "confidence": confidence})
    return {
        "mode": "DEMO_IMAGE_HEURISTIC",
        "detected_defects": defects,
        "defect_score": round(score, 4),
        "defective_area_pct": defective_area,
        "usable_area_pct": round(100.0 - defective_area, 2),
        "suggested_grade": _grade(score),
        "confidence": confidence,
        "annotated_image": None,
        "notice": "Demo heuristic only; replace with a trained and validated leather-defect model for real use.",
    }
