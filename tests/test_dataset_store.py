from datetime import datetime, timezone

import pytest

from app.domain.history import DatasetManifest, HistoricalSetup
from app.domain.market import Instrument
from history.datasets.store import DatasetNotFoundError, DatasetStore, HistoricalDataset

INSTRUMENT = Instrument(symbol="XYZ", exchange="NSE")


def _manifest(version="v1") -> DatasetManifest:
    return DatasetManifest(
        dataset_version=version,
        source="test",
        created_at=datetime.now(timezone.utc),
        date_range_start=datetime(2020, 1, 1, tzinfo=timezone.utc),
        date_range_end=datetime(2026, 1, 1, tzinfo=timezone.utc),
        universe_definition="NSE 50-300",
        feature_schema=("rsi", "relative_volume"),
        label_definition="forward return by horizon",
        configuration_snapshot="{}",
    )


def _setup(version="v1") -> HistoricalSetup:
    return HistoricalSetup(
        instrument=INSTRUMENT,
        timestamp=datetime.now(timezone.utc),
        price=100.0,
        volume=1000,
        relative_volume=1.5,
        volatility=0.02,
        trend="uptrend",
        rsi=60.0,
        vwap=99.0,
        market_state="RISK_ON",
        sector_state=None,
        pattern="MOMENTUM",
        event_context=None,
        dataset_version=version,
        features={"rsi": 60.0, "relative_volume": 1.5},
    )


def test_manifest_rejects_inverted_date_range():
    with pytest.raises(ValueError):
        DatasetManifest(
            dataset_version="v1", source="test",
            created_at=datetime.now(timezone.utc),
            date_range_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            date_range_end=datetime(2020, 1, 1, tzinfo=timezone.utc),
            universe_definition="x", feature_schema=(), label_definition="x",
            configuration_snapshot="{}",
        )


def test_manifest_content_hash_is_deterministic():
    m1 = _manifest()
    m2 = _manifest()
    assert m1.content_hash() == m2.content_hash()


def test_dataset_rejects_setup_with_mismatched_version():
    with pytest.raises(ValueError):
        HistoricalDataset(manifest=_manifest("v1"), setups=[_setup("v2")])


def test_store_save_and_get_roundtrip():
    store = DatasetStore()
    dataset = HistoricalDataset(manifest=_manifest("v1"), setups=[_setup("v1")])
    store.save(dataset)
    fetched = store.get("v1")
    assert fetched.setups[0].instrument.symbol == "XYZ"


def test_store_get_missing_raises():
    store = DatasetStore()
    with pytest.raises(DatasetNotFoundError):
        store.get("nope")
