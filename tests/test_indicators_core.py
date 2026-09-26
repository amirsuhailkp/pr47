from datetime import datetime, timedelta, timezone

from app.domain.market import Instrument, OHLCVBar
from market.indicators import core


def _bar(close: float, high: float, low: float, volume: int, i: int) -> OHLCVBar:
    ts = datetime(2026, 9, 21, 9, 15, tzinfo=timezone.utc) + timedelta(minutes=i)
    return OHLCVBar(
        instrument=Instrument(symbol="XYZ", exchange="NSE"),
        interval="1m",
        open=close,
        high=high,
        low=low,
        close=close,
        volume=volume,
        timestamp=ts,
        source="test",
        ingestion_timestamp=ts,
    )


def test_sma_basic():
    assert core.sma([1, 2, 3, 4, 5], 5) == 3.0
    assert core.sma([1, 2], 5) is None


def test_ema_matches_sma_seed_then_diverges():
    values = [1, 2, 3, 4, 5, 6]
    series = core.ema_series(values, 3)
    assert series[0] == core.sma(values[:3], 3)
    assert len(series) == len(values) - 3 + 1


def test_rolling_return():
    values = [100, 105, 110]
    ret = core.rolling_return(values, 2)
    assert round(ret, 2) == 10.0


def test_rsi_all_gains_is_100():
    closes = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24]
    assert core.rsi(closes, 14) == 100.0


def test_rsi_insufficient_data_is_none():
    assert core.rsi([1, 2, 3], 14) is None


def test_atr_requires_period_plus_one_bars():
    bars = [_bar(100 + i, 101 + i, 99 + i, 1000, i) for i in range(10)]
    assert core.atr(bars, 14) is None
    bars = [_bar(100 + i, 101 + i, 99 + i, 1000, i) for i in range(15)]
    assert core.atr(bars, 14) is not None


def test_vwap_weighted_by_volume():
    bars = [
        _bar(100, 101, 99, 1000, 0),
        _bar(110, 111, 109, 3000, 1),
    ]
    v = core.vwap(bars)
    assert v is not None
    assert 100 < v < 110  # pulled toward the higher-volume bar


def test_breakout_distance_positive_above_resistance():
    assert core.breakout_distance_pct(105, 100) == 5.0
    assert core.breakout_distance_pct(95, 100) == -5.0


def test_drawdown_from_peak():
    dd = core.drawdown_pct([100, 110, 105])
    assert round(dd, 2) == round((105 - 110) / 110 * 100, 2)
