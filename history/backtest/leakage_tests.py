"""Automated leakage checks (docs §23, §40: "create automated leakage tests").

These are assertion-style functions meant to be called from tests and, longer-term,
from CI as a gate on any dataset/split before it's used for training or backtesting.
Each raises a LeakageError with a specific, actionable message rather than returning
a bare bool, so a CI failure explains itself.
"""
from __future__ import annotations

from history.backtest.validation import Split


class LeakageError(Exception):
    pass


def assert_no_temporal_overlap(split: Split, get_timestamp) -> None:
    """The split is chronological: every train timestamp must precede every test
    timestamp. Catches accidental random splitting or a mis-ordered join."""
    if not split.train or not split.test:
        return
    max_train_ts = max(get_timestamp(i) for i in split.train)
    min_test_ts = min(get_timestamp(i) for i in split.test)
    if max_train_ts >= min_test_ts:
        raise LeakageError(
            f"temporal overlap: latest train timestamp {max_train_ts} is not before "
            f"earliest test timestamp {min_test_ts}"
        )


def assert_no_duplicate_items(split: Split, get_key) -> None:
    """No single sample (by its identity key) appears in both train and test."""
    train_keys = {get_key(i) for i in split.train}
    test_keys = {get_key(i) for i in split.test}
    overlap = train_keys & test_keys
    if overlap:
        raise LeakageError(f"{len(overlap)} item(s) appear in both train and test: {overlap}")


def assert_outcome_uses_only_forward_data(setup_timestamp, outcome_bar_timestamps: list) -> None:
    """Every bar used to compute an outcome must be strictly after the setup's own
    timestamp — mirrors the runtime check in history/outcomes/calculator.py, kept
    here too so it can be exercised as a standalone, dataset-wide leakage test."""
    bad = [ts for ts in outcome_bar_timestamps if ts <= setup_timestamp]
    if bad:
        raise LeakageError(
            f"{len(bad)} outcome bar(s) at or before the setup timestamp "
            f"{setup_timestamp} — this would leak same-period or past data as a "
            "'future' outcome"
        )


def assert_feature_schema_matches_manifest(
    feature_keys: set[str], manifest_feature_schema: tuple[str, ...]
) -> None:
    """A dataset's stored features must match exactly what its manifest declares —
    an undeclared feature is untracked provenance, which is its own leakage risk
    (you can no longer prove what information a model actually saw)."""
    declared = set(manifest_feature_schema)
    undeclared = feature_keys - declared
    if undeclared:
        raise LeakageError(
            f"feature(s) present but not declared in the manifest schema: {undeclared}"
        )
