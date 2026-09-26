from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from history.backtest.leakage_tests import (
    LeakageError,
    assert_feature_schema_matches_manifest,
    assert_no_duplicate_items,
    assert_no_temporal_overlap,
    assert_outcome_uses_only_forward_data,
)
from history.backtest.validation import Split


@dataclass(frozen=True)
class Item:
    idx: int
    timestamp: datetime


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_no_temporal_overlap_passes_for_clean_split():
    train = [Item(0, BASE), Item(1, BASE + timedelta(days=1))]
    test = [Item(2, BASE + timedelta(days=2))]
    assert_no_temporal_overlap(Split(train, test), lambda i: i.timestamp)  # no raise


def test_no_temporal_overlap_raises_when_train_reaches_into_test():
    train = [Item(0, BASE), Item(1, BASE + timedelta(days=5))]
    test = [Item(2, BASE + timedelta(days=2))]
    with pytest.raises(LeakageError):
        assert_no_temporal_overlap(Split(train, test), lambda i: i.timestamp)


def test_no_duplicate_items_raises_on_shared_key():
    train = [Item(0, BASE), Item(1, BASE)]
    test = [Item(1, BASE)]
    with pytest.raises(LeakageError):
        assert_no_duplicate_items(Split(train, test), lambda i: i.idx)


def test_no_duplicate_items_passes_when_disjoint():
    train = [Item(0, BASE)]
    test = [Item(1, BASE)]
    assert_no_duplicate_items(Split(train, test), lambda i: i.idx)  # no raise


def test_outcome_forward_data_check_raises_on_same_or_earlier_bar():
    with pytest.raises(LeakageError):
        assert_outcome_uses_only_forward_data(BASE, [BASE - timedelta(days=1), BASE + timedelta(days=1)])


def test_outcome_forward_data_check_passes_when_strictly_after():
    assert_outcome_uses_only_forward_data(
        BASE, [BASE + timedelta(days=1), BASE + timedelta(days=2)]
    )  # no raise


def test_feature_schema_check_raises_on_undeclared_feature():
    with pytest.raises(LeakageError):
        assert_feature_schema_matches_manifest({"rsi", "secret_feature"}, ("rsi",))


def test_feature_schema_check_passes_when_matching():
    assert_feature_schema_matches_manifest({"rsi", "relative_volume"}, ("rsi", "relative_volume"))
