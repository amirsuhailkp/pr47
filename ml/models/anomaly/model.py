"""Anomaly detection (ML task 1 of 6, docs/ML_ARCHITECTURE.md).

A per-feature z-score model, fit only on training data (chronological — see
ml/training/train_anomaly.py). Deliberately simple and fully explainable: the score
always carries its per-feature contributions, never a bare number (docs §45 "no blind
scoring" applies to ML output as much as to alerts).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AnomalyScore:
    combined_z: float
    per_feature_z: dict[str, float]

    def top_contributors(self, n: int = 3) -> list[tuple[str, float]]:
        return sorted(self.per_feature_z.items(), key=lambda kv: abs(kv[1]), reverse=True)[:n]


@dataclass
class AnomalyModel:
    """Fit stores per-feature (mean, std) from training data only."""

    feature_schema: tuple[str, ...]
    means: dict[str, float] = field(default_factory=dict)
    stds: dict[str, float] = field(default_factory=dict)
    sample_size: int = 0

    @classmethod
    def fit(cls, training_features: list[dict[str, float]], feature_schema: tuple[str, ...]) -> "AnomalyModel":
        if not training_features:
            raise ValueError("AnomalyModel.fit requires at least one training example")

        means: dict[str, float] = {}
        stds: dict[str, float] = {}
        for key in feature_schema:
            values = [f[key] for f in training_features if key in f]
            if not values:
                continue
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            means[key] = mean
            stds[key] = math.sqrt(variance)

        return cls(
            feature_schema=feature_schema, means=means, stds=stds, sample_size=len(training_features)
        )

    def to_dict(self) -> dict:
        """Plain-JSON serialization so a trained model survives a process restart
        (e.g. an Azure redeploy) without needing a database migration — see
        ml/registry/persistence.py."""
        return {
            "feature_schema": list(self.feature_schema),
            "means": self.means,
            "stds": self.stds,
            "sample_size": self.sample_size,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AnomalyModel":
        return cls(
            feature_schema=tuple(data["feature_schema"]),
            means=dict(data["means"]),
            stds=dict(data["stds"]),
            sample_size=int(data["sample_size"]),
        )

    def score(self, features: dict[str, float]) -> AnomalyScore:
        per_feature_z: dict[str, float] = {}
        for key in self.feature_schema:
            if key not in features or key not in self.means:
                continue
            std = self.stds.get(key, 0.0)
            if std == 0:
                continue
            per_feature_z[key] = (features[key] - self.means[key]) / std

        if not per_feature_z:
            return AnomalyScore(combined_z=0.0, per_feature_z={})

        combined = math.sqrt(sum(z * z for z in per_feature_z.values()) / len(per_feature_z))
        return AnomalyScore(combined_z=combined, per_feature_z=per_feature_z)


@dataclass
class BaselineAnomalyModel:
    """The baseline every AnomalyModel must beat: a single fixed threshold on one
    feature, with no training and no per-feature nuance."""

    feature_key: str = "relative_volume"
    threshold: float = 2.0

    def score(self, features: dict[str, float]) -> AnomalyScore:
        value = features.get(self.feature_key, 0.0)
        z = value / self.threshold if self.threshold else 0.0
        return AnomalyScore(combined_z=z, per_feature_z={self.feature_key: z})
