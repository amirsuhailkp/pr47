"""Persists the current PRODUCTION anomaly model to a plain JSON file.

ml/registry/registry.py is explicitly an in-memory scaffold (its own docstring says
so) — it tracks manifests/validation/status but never the model's actual weights, and
none of it survives a process restart. On Azure, where nobody is watching the process
to re-run training after every redeploy, that means every restart would silently drop
back to the untrained fallback with no visible sign anything changed. This file is the
small, boring fix: one JSON blob with the model + the manifest/validation that justified
promoting it, read back on startup.

A durable store (blob storage, a DB table) can replace the file path here later without
changing the two function signatures below.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.domain.ml import ModelManifest, ValidationResult
from ml.models.anomaly.model import AnomalyModel

DEFAULT_PATH = Path("data/models/anomaly_production.json")

LAST_ATTEMPT_PATH = Path("data/models/anomaly_last_attempt.txt")
"""Tracks when a retrain was last *attempted*, independent of whether it was
promoted. scripts/run_service.py's retrain scheduler used to gate purely on
DEFAULT_PATH's mtime — fine once a model has ever been promoted, but if promotion
never succeeds (e.g. a model that never beats its baseline), DEFAULT_PATH never gets
created, so that gate was always skipped and it retrained on every single poll cycle
forever instead of once every RETRAIN_INTERVAL_DAYS. This file closes that gap."""


def record_retrain_attempt(when: datetime | None = None, path: Path = LAST_ATTEMPT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((when or datetime.now(timezone.utc)).isoformat())


def days_since_last_attempt(path: Path = LAST_ATTEMPT_PATH) -> float | None:
    """None means "never attempted" — callers should treat that as due immediately."""
    if not path.exists():
        return None
    last = datetime.fromisoformat(path.read_text().strip())
    return (datetime.now(timezone.utc) - last).total_seconds() / 86400


def save_production_anomaly_model(
    model: AnomalyModel,
    manifest: ModelManifest,
    validation: ValidationResult,
    path: Path = DEFAULT_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": model.to_dict(),
        "manifest": {**asdict(manifest), "trained_at": manifest.trained_at.isoformat()},
        "validation": asdict(validation),
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2))


def load_production_anomaly_model(
    path: Path = DEFAULT_PATH,
) -> tuple[AnomalyModel, ModelManifest, ValidationResult] | None:
    """Returns None (not an error) if nothing has been trained and promoted yet —
    callers fall back to the online-fit detector in that case, per
    patterns/anomaly/detector.py's docstring."""
    if not path.exists():
        return None

    data = json.loads(path.read_text())
    model = AnomalyModel.from_dict(data["model"])
    manifest_data = dict(data["manifest"])
    manifest_data["trained_at"] = datetime.fromisoformat(manifest_data["trained_at"])
    manifest_data["feature_schema"] = tuple(manifest_data["feature_schema"])
    manifest = ModelManifest(**manifest_data)
    validation = ValidationResult(**data["validation"])
    return model, manifest, validation
