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
