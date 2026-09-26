from datetime import datetime, timezone

from app.domain.market import IndexSnapshot, Instrument
from app.domain.patterns import Severity
from market.analytics.context import build_context
from market.analytics.price_volume import PriceVolumeSnapshot
from patterns.engine.events import detect_all_events, detect_price_events, detect_volume_events

NOW = datetime.now(timezone.utc)
INSTRUMENT = Instrument(symbol="XYZ", exchange="NSE")


def _snapshot(**overrides) -> PriceVolumeSnapshot:
    defaults = dict(
        price=150.0, price_change_pct=1.0, relative_volume=1.0, volume_acceleration=1.0,
        rsi_14=50.0, atr_14=2.0, sma_20=145.0, sma_50=140.0, ema_20=146.0, vwap=148.0,
        distance_from_vwap_pct=1.0, distance_from_sma20_pct=3.0, recent_high_20=149.0,
        recent_low_20=130.0, breakout_distance_pct=-1.0, drawdown_pct=-1.0,
    )
    defaults.update(overrides)
    return PriceVolumeSnapshot(**defaults)


def test_no_price_event_below_threshold():
    snap = _snapshot(price_change_pct=1.0)
    assert detect_price_events(INSTRUMENT, snap, NOW) == []


def test_rapid_price_event_is_important():
    snap = _snapshot(price_change_pct=4.0)
    events = detect_price_events(INSTRUMENT, snap, NOW)
    assert len(events) == 1
    assert events[0].severity == Severity.IMPORTANT


def test_extreme_price_event_is_critical():
    snap = _snapshot(price_change_pct=-8.0)
    events = detect_price_events(INSTRUMENT, snap, NOW)
    assert events[0].severity == Severity.CRITICAL
    assert "decrease" in events[0].description


def test_extreme_relative_volume_is_critical():
    snap = _snapshot(relative_volume=5.0)
    events = detect_volume_events(INSTRUMENT, snap, NOW)
    assert any(e.severity == Severity.CRITICAL for e in events)


def test_unusual_relative_volume_is_watch():
    snap = _snapshot(relative_volume=2.5)
    events = detect_volume_events(INSTRUMENT, snap, NOW)
    assert any(e.severity == Severity.WATCH for e in events)


def test_detect_all_events_includes_market_context():
    snap = _snapshot(price_change_pct=4.0, relative_volume=3.0)
    idx = IndexSnapshot(
        code="NIFTY50", value=20000, change=400, change_pct=2.0, timestamp=NOW, source="test"
    )
    ctx = build_context(4.0, idx, None, market_volatility=2.0)  # forces HIGH_VOLATILITY
    events = detect_all_events(INSTRUMENT, snap, ctx, NOW)
    categories = {e.category.value for e in events}
    assert "PRICE" in categories
    assert "VOLUME" in categories
    assert "MARKET" in categories
