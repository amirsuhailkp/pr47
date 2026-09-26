from datetime import datetime, timedelta, timezone

from app.domain.history import DatasetManifest, HistoricalSetup
from app.domain.market import Instrument, OHLCVBar
from history.datasets.store import DatasetStore, HistoricalDataset
from history.outcomes.calculator import compute_outcome
from history.similarity.matcher import find_similar
from history.statistics.summary import summarize

INSTRUMENT = Instrument(symbol="XYZ", exchange="NSE")
BASE = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _manifest() -> DatasetManifest:
    return DatasetManifest(
        dataset_version="v1", source="test", created_at=datetime.now(timezone.utc),
        date_range_start=BASE, date_range_end=BASE + timedelta(days=400),
        universe_definition="NSE 50-300", feature_schema=("rsi", "relative_volume"),
        label_definition="forward return", configuration_snapshot="{}",
    )


def _setup(day_offset: int, rsi: float, rel_vol: float, price: float = 100.0) -> HistoricalSetup:
    return HistoricalSetup(
        instrument=INSTRUMENT, timestamp=BASE + timedelta(days=day_offset), price=price,
        volume=1000, relative_volume=rel_vol, volatility=0.02, trend="uptrend", rsi=rsi,
        vwap=price * 0.99, market_state="RISK_ON", sector_state=None, pattern="MOMENTUM",
        event_context=None, dataset_version="v1", features={"rsi": rsi, "relative_volume": rel_vol},
    )


def _forward_bars(start_offset: int, closes: list[float]) -> list[OHLCVBar]:
    out = []
    for i, c in enumerate(closes):
        ts = BASE + timedelta(days=start_offset + i + 1)
        out.append(
            OHLCVBar(
                instrument=INSTRUMENT, interval="1d", open=c, high=c * 1.01, low=c * 0.99,
                close=c, volume=1000, timestamp=ts, source="test", ingestion_timestamp=ts,
            )
        )
    return out


def test_full_historical_engine_pipeline():
    # 1. Store a dataset of historical momentum-like setups (with a manifest).
    setups = [
        _setup(0, rsi=65.0, rel_vol=2.0),
        _setup(10, rsi=68.0, rel_vol=2.2),
        _setup(20, rsi=30.0, rel_vol=0.5),  # dissimilar — shouldn't match the query
    ]
    dataset = HistoricalDataset(manifest=_manifest(), setups=setups)
    store = DatasetStore()
    store.save(dataset)

    # 2. Find setups similar to today's live situation.
    query = {"rsi": 66.0, "relative_volume": 2.1}
    scales = {"rsi": 15.0, "relative_volume": 1.0}
    fetched = store.get("v1")
    matches = find_similar(query, fetched.setups, scales, top_n=5, max_distance=1.0)
    assert len(matches) == 2
    matched_setups = [m.setup for m in matches]

    # 3. Compute forward outcomes for the matched setups (strictly forward-only bars).
    outcomes = []
    for setup in matched_setups:
        offset = int((setup.timestamp - BASE).days)
        bars = _forward_bars(offset, [101, 102, 103, 104, 105])
        outcome = compute_outcome(setup, bars, "5d")
        assert outcome is not None
        outcomes.append(outcome)

    # 4. Summarize — never a single number, always sample size + distribution.
    summary = summarize("momentum-like setup", {"5d": outcomes})
    assert summary.sample_size == 2
    horizon_summary = summary.horizons["5d"]
    assert horizon_summary.sample_size == 2
    assert len(horizon_summary.return_distribution) == 2
    assert "small sample" in horizon_summary.uncertainty_note.lower()
