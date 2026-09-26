from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from history.backtest.validation import chronological_split, purge_embargo, walk_forward_splits


@dataclass(frozen=True)
class Item:
    idx: int
    timestamp: datetime


def _items(n: int, step_days: int = 1) -> list[Item]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [Item(i, base + timedelta(days=i * step_days)) for i in range(n)]


def _ts(item: Item) -> datetime:
    return item.timestamp


def test_chronological_split_preserves_order_no_shuffling():
    items = _items(10)
    split = chronological_split(items, _ts, train_fraction=0.7)
    assert [i.idx for i in split.train] == list(range(7))
    assert [i.idx for i in split.test] == list(range(7, 10))


def test_chronological_split_train_always_before_test():
    items = _items(20)
    split = chronological_split(items, _ts, train_fraction=0.5)
    assert max(_ts(i) for i in split.train) < min(_ts(i) for i in split.test)


def test_purge_embargo_removes_boundary_items():
    items = _items(10)
    split = chronological_split(items, _ts, train_fraction=0.7)
    purged = purge_embargo(split, _ts, embargo=timedelta(days=2))
    # items right at the boundary (idx 6, and test idx 7) should be dropped
    assert 6 not in [i.idx for i in purged.train]
    assert len(purged.train) < len(split.train)


def test_walk_forward_splits_are_chronological_and_non_overlapping_targets():
    items = _items(100)
    splits = walk_forward_splits(items, _ts, n_splits=4, min_train_fraction=0.3)
    assert len(splits) == 4
    for split in splits:
        assert max(_ts(i) for i in split.train) < min(_ts(i) for i in split.test)
    # each split's train set grows (rolling origin)
    sizes = [len(s.train) for s in splits]
    assert sizes == sorted(sizes)
