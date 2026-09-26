"""Similarity search over stored historical setups.

Deliberately simple and explainable (normalized Euclidean distance over a shared
feature schema) rather than a black-box similarity model — see docs/ML_ARCHITECTURE.md:
a proper learned similarity model is an optional, independently-scoped ML task, not a
requirement for the deterministic path to work.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app.domain.history import HistoricalSetup


@dataclass(frozen=True)
class SimilarityMatch:
    setup: HistoricalSetup
    distance: float


def _normalized_distance(
    query: dict[str, float], candidate: dict[str, float], feature_scales: dict[str, float]
) -> float | None:
    shared_keys = set(query) & set(candidate) & set(feature_scales)
    if not shared_keys:
        return None
    total = 0.0
    for key in shared_keys:
        scale = feature_scales[key]
        if scale == 0:
            continue
        diff = (query[key] - candidate[key]) / scale
        total += diff * diff
    return math.sqrt(total)


def find_similar(
    query_features: dict[str, float],
    candidates: list[HistoricalSetup],
    feature_scales: dict[str, float],
    top_n: int = 20,
    max_distance: float | None = None,
) -> list[SimilarityMatch]:
    """Ranks candidates by distance to the query feature vector, closest first.

    `feature_scales` should hold a typical spread (e.g. std dev) per feature so no
    single high-magnitude feature dominates the distance — callers own this choice,
    it is never inferred silently.
    """
    matches: list[SimilarityMatch] = []
    for candidate in candidates:
        distance = _normalized_distance(query_features, candidate.features, feature_scales)
        if distance is None:
            continue
        if max_distance is not None and distance > max_distance:
            continue
        matches.append(SimilarityMatch(setup=candidate, distance=distance))

    matches.sort(key=lambda m: m.distance)
    return matches[:top_n]
