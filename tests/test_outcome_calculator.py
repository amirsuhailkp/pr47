from datetime import datetime, timedelta, timezone

import pytest

from app.domain.history import HistoricalSetup
from app.domain.market import Instrument, OHLCVBar
from history.outcomes.calculator import compute_outcome

INSTRUMENT = Instrument(symbol="XYZ", exchange="NSE")
BASE_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _setup(price=100.0, ts=BASE_TS) -> HistoricalSetup:
    return HistoricalSetup(
        instrument=INSTRUMENT, timestamp=ts, price=price, volume=1000, relative_volume=1.5,
        volatility=0.02, trend="uptrend", rsi=60.0, vwap=99.0, market_state=None,
        sector_state=None, pattern="MOMENTUM", event_context=None, dataset_version="v1",
    )


def _bar(close, high, low, i) -> OHLCVBar:
    ts = BASE_TS + timedelta(days=i + 1)
    return OHLCVBar(
        instrument=INSTRUMENT, interval="1d", open=close, high=high, low=low, close=close,
        volume=1000, timestamp=ts, source="test", ingestion_timestamp=ts,
    )


def test_returns_none_when_not_enough_forward_bars():
    setup = _setup()
    bars = [_bar(101, 102, 100, 0)]
    assert compute_outcome(setup, bars, "5d") is None


def test_computes_return_and_excursions():
    setup = _setup(price=100.0)
    bars = [_bar(105, 106, 99, i) for i in range(5)]
    outcome = compute_outcome(setup, bars, "5d")
    assert outcome is not None
    assert round(outcome.return_pct, 2) == 5.0
    assert outcome.max_favorable_excursion_pct == 6.0
    assert outcome.max_adverse_excursion_pct == -1.0


def test_rejects_forward_bars_at_or_before_setup_timestamp():
    setup = _setup(ts=BASE_TS)
    bad_bar = OHLCVBar(
        instrument=INSTRUMENT, interval="1d", open=100, high=101, low=99, close=100,
        volume=1000, timestamp=BASE_TS, source="test", ingestion_timestamp=BASE_TS,
    )
    with pytest.raises(ValueError):
        compute_outcome(setup, [bad_bar], "1d")


def test_unknown_horizon_raises():
    with pytest.raises(ValueError):
        compute_outcome(_setup(), [_bar(101, 102, 100, 0)], "42d")
