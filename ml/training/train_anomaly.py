"""Trains and validates an AnomalyModel end to end.

Enforces the requirements in docs/ML_ARCHITECTURE.md: chronological (never random)
split, an explicit baseline to beat, automated leakage tests before anything is
considered valid, and a full ModelManifest + ValidationResult for the registry.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from app.domain.ml import ModelManifest, ValidationResult
from history.backtest.leakage_tests import assert_no_temporal_overlap
from history.backtest.validation import Split, chronological_split
from ml.evaluation.ranking_metrics import precision_at_k
from ml.models.anomaly.model import AnomalyModel, BaselineAnomalyModel


@dataclass(frozen=True)
class TrainingExample:
    timestamp: datetime
    features: dict[str, float]
    forward_return_pct: float  # from history/outcomes — used only as the eval label


def train_and_validate_anomaly_model(
    examples: list[TrainingExample],
    feature_schema: tuple[str, ...],
    model_version: str,
    anomaly_return_threshold_pct: float = 5.0,
    top_k: int = 10,
    train_fraction: float = 0.7,
) -> tuple[AnomalyModel, ModelManifest, ValidationResult]:
    if len(examples) < 10:
        raise ValueError("need at least 10 examples for a meaningful chronological split")

    split: Split[TrainingExample] = chronological_split(
        examples, lambda e: e.timestamp, train_fraction=train_fraction
    )
    assert_no_temporal_overlap(split, lambda e: e.timestamp)  # leakage gate

    model = AnomalyModel.fit([e.features for e in split.train], feature_schema)
    baseline = BaselineAnomalyModel()

    def is_positive(e: TrainingExample) -> bool:
        return abs(e.forward_return_pct) >= anomaly_return_threshold_pct

    model_precision = precision_at_k(
        split.test, lambda e: model.score(e.features).combined_z, is_positive, top_k
    )
    baseline_precision = precision_at_k(
        split.test, lambda e: baseline.score(e.features).combined_z, is_positive, top_k
    )

    manifest = ModelManifest(
        task="anomaly_detection",
        model_version=model_version,
        feature_schema=feature_schema,
        target_definition=(
            f"forward return magnitude >= {anomaly_return_threshold_pct}% "
            "(used only as an evaluation label, never as a training feature)"
        ),
        training_data_description=f"{len(split.train)} chronological examples",
        trained_at=datetime.now(timezone.utc),
        training_metadata={"train_fraction": str(train_fraction), "top_k": str(top_k)},
    )

    validation = ValidationResult(
        model_version=model_version,
        baseline_metric=baseline_precision,
        model_metric=model_precision,
        metric_name=f"precision_at_{top_k}",
        higher_is_better=True,
        sample_size=len(split.test),
        leakage_tests_passed=True,  # assert_no_temporal_overlap above didn't raise
    )

    return model, manifest, validation
