"""ML model lifecycle models — docs/ML_ARCHITECTURE.md.

Every model is independently scoped and versioned; promotion to production is a
deliberate, logged action gated on chronological validation clearing a baseline and
passing leakage tests — never automatic on training completion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


def _require_aware(ts: datetime, field_name: str) -> None:
    if ts.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware, got naive datetime")


class ModelStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    PRODUCTION = "PRODUCTION"
    RETIRED = "RETIRED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ModelManifest:
    """Required metadata for any trained model — mirrors DatasetManifest's discipline."""

    task: str  # one of the six ML tasks in docs/ML_ARCHITECTURE.md
    model_version: str
    feature_schema: tuple[str, ...]
    target_definition: str
    training_data_description: str
    trained_at: datetime
    training_metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_aware(self.trained_at, "trained_at")


@dataclass(frozen=True)
class ValidationResult:
    """Chronological/walk-forward validation outcome for one model version."""

    model_version: str
    baseline_metric: float
    model_metric: float
    metric_name: str  # e.g. "accuracy", "mae" — lower-is-better vs higher-is-better
    higher_is_better: bool
    sample_size: int
    leakage_tests_passed: bool
    notes: str = ""

    @property
    def beats_baseline(self) -> bool:
        if self.higher_is_better:
            return self.model_metric > self.baseline_metric
        return self.model_metric < self.baseline_metric

    @property
    def eligible_for_promotion(self) -> bool:
        return self.leakage_tests_passed and self.beats_baseline


@dataclass
class RegistryEntry:
    manifest: ModelManifest
    validation: ValidationResult | None
    status: ModelStatus = ModelStatus.CANDIDATE
    promoted_at: datetime | None = None
