"""Ranking evaluation — precision@k, used to compare a candidate model against its
baseline (docs/ML_ARCHITECTURE.md: promotion requires beating a defined baseline).
"""
from __future__ import annotations

from typing import Callable, TypeVar

T = TypeVar("T")


def precision_at_k(
    items: list[T],
    score_fn: Callable[[T], float],
    is_positive_fn: Callable[[T], bool],
    k: int,
) -> float:
    """Ranks items by score_fn descending, then measures what fraction of the top-k
    are true positives per is_positive_fn. Returns 0.0 if items is empty."""
    if not items:
        return 0.0
    ranked = sorted(items, key=score_fn, reverse=True)
    top_k = ranked[: min(k, len(ranked))]
    if not top_k:
        return 0.0
    positives = sum(1 for item in top_k if is_positive_fn(item))
    return positives / len(top_k)
