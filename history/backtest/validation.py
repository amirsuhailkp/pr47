"""Chronological validation for time-series data — never random splits (docs §23, §25).

Provides:
- chronological_split: a single ordered train/test cut
- walk_forward_splits: rolling-origin splits for more robust validation
- purge/embargo: removes samples near the train/test boundary whose labels could
  overlap into the other side, which is the classic source of subtle leakage in
  overlapping-label financial datasets.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Generic, Protocol, TypeVar


class HasTimestamp(Protocol):
    timestamp: object  # datetime, checked at runtime by callers


T = TypeVar("T")


@dataclass(frozen=True)
class Split(Generic[T]):
    train: list[T]
    test: list[T]


def chronological_split(items: list[T], get_timestamp, train_fraction: float = 0.7) -> Split[T]:
    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between 0 and 1")
    ordered = sorted(items, key=get_timestamp)
    cut = int(len(ordered) * train_fraction)
    return Split(train=ordered[:cut], test=ordered[cut:])


def purge_embargo(
    split: Split[T],
    get_timestamp,
    embargo: timedelta,
) -> Split[T]:
    """Drops train items whose timestamp falls within `embargo` of the first test
    timestamp, and test items within `embargo` of the last train timestamp — removing
    the boundary zone where overlapping labels could leak across the split."""
    if not split.train or not split.test:
        return split

    first_test_ts = get_timestamp(min(split.test, key=get_timestamp))
    last_train_ts = get_timestamp(max(split.train, key=get_timestamp))

    purged_train = [
        item for item in split.train if get_timestamp(item) <= first_test_ts - embargo
    ]
    purged_test = [
        item for item in split.test if get_timestamp(item) >= last_train_ts + embargo
    ]
    return Split(train=purged_train, test=purged_test)


def walk_forward_splits(
    items: list[T], get_timestamp, n_splits: int, min_train_fraction: float = 0.3
) -> list[Split[T]]:
    """Rolling-origin splits: each successive split trains on everything up to a
    growing cutoff and tests on the next slice — never on data from its own future."""
    if n_splits < 1:
        raise ValueError("n_splits must be at least 1")
    ordered = sorted(items, key=get_timestamp)
    n = len(ordered)
    min_train = int(n * min_train_fraction)
    remaining = n - min_train
    if remaining <= 0:
        return []

    step = max(remaining // n_splits, 1)
    splits: list[Split[T]] = []
    cutoff = min_train
    for _ in range(n_splits):
        test_end = min(cutoff + step, n)
        if cutoff >= test_end:
            break
        splits.append(Split(train=ordered[:cutoff], test=ordered[cutoff:test_end]))
        cutoff = test_end
    return splits
