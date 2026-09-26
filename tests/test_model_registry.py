from datetime import datetime, timezone

import pytest

from app.domain.ml import ModelManifest, ModelStatus, ValidationResult
from ml.registry.registry import ModelNotFoundError, ModelRegistry, PromotionNotEligibleError

NOW = datetime.now(timezone.utc)


def _manifest(version="v1") -> ModelManifest:
    return ModelManifest(
        task="anomaly_detection", model_version=version, feature_schema=("a",),
        target_definition="test", training_data_description="test", trained_at=NOW,
    )


def _validation(version="v1", beats=True, leakage_ok=True) -> ValidationResult:
    return ValidationResult(
        model_version=version, baseline_metric=0.3, model_metric=(0.5 if beats else 0.1),
        metric_name="precision", higher_is_better=True, sample_size=100,
        leakage_tests_passed=leakage_ok,
    )


def test_register_and_get_roundtrip():
    registry = ModelRegistry()
    registry.register(_manifest())
    entry = registry.get("anomaly_detection", "v1")
    assert entry.status == ModelStatus.CANDIDATE


def test_get_missing_raises():
    registry = ModelRegistry()
    with pytest.raises(ModelNotFoundError):
        registry.get("anomaly_detection", "nope")


def test_promotion_requires_validation():
    registry = ModelRegistry()
    registry.register(_manifest())
    with pytest.raises(PromotionNotEligibleError):
        registry.promote("anomaly_detection", "v1")


def test_promotion_requires_beating_baseline():
    registry = ModelRegistry()
    registry.register(_manifest(), _validation(beats=False))
    with pytest.raises(PromotionNotEligibleError):
        registry.promote("anomaly_detection", "v1")


def test_promotion_requires_leakage_tests_passed():
    registry = ModelRegistry()
    registry.register(_manifest(), _validation(leakage_ok=False))
    with pytest.raises(PromotionNotEligibleError):
        registry.promote("anomaly_detection", "v1")


def test_successful_promotion():
    registry = ModelRegistry()
    registry.register(_manifest(), _validation())
    registry.promote("anomaly_detection", "v1", now=NOW)
    entry = registry.get("anomaly_detection", "v1")
    assert entry.status == ModelStatus.PRODUCTION
    assert entry.promoted_at == NOW
    assert registry.production_model("anomaly_detection") is entry


def test_promoting_new_version_retires_old_production_model():
    registry = ModelRegistry()
    registry.register(_manifest("v1"), _validation("v1"))
    registry.promote("anomaly_detection", "v1")

    registry.register(_manifest("v2"), _validation("v2"))
    registry.promote("anomaly_detection", "v2")

    assert registry.get("anomaly_detection", "v1").status == ModelStatus.RETIRED
    assert registry.get("anomaly_detection", "v2").status == ModelStatus.PRODUCTION
    assert registry.production_model("anomaly_detection").manifest.model_version == "v2"


def test_reject_sets_status():
    registry = ModelRegistry()
    registry.register(_manifest())
    registry.reject("anomaly_detection", "v1")
    assert registry.get("anomaly_detection", "v1").status == ModelStatus.REJECTED
