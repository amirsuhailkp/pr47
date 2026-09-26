from datetime import datetime, timezone

import pytest

from app.domain.market import IndexSnapshot, Instrument
from market.analytics.context import build_context
from market.analytics.price_volume import PriceVolumeSnapshot
from patterns.breakout.detector import BreakoutDetector
from patterns.engine.base import PatternEngine
from patterns.momentum.detector import MomentumDetector
from patterns.pullback.detector import PullbackDetector

NOW = datetime.now(timezone.utc)
INSTRUMENT = Instrument(symbol="XYZ", exchange="NSE")


def _snapshot(**overrides) -> PriceVolumeSnapshot:
    defaults = dict(
        price=150.0,
        price_change_pct=1.0,
        relative_volume=1.0,
        volume_acceleration=1.0,
        rsi_14=50.0,
        atr_14=2.0,
        sma_20=145.0,
        sma_50=140.0,
        ema_20=146.0,
        vwap=148.0,
        distance_from_vwap_pct=1.0,
        distance_from_sma20_pct=3.0,
        recent_high_20=149.0,
        recent_low_20=130.0,
        breakout_distance_pct=0.5,
        drawdown_pct=-1.0,
    )
    defaults.update(overrides)
    return PriceVolumeSnapshot(**defaults)


def _market_context(stock_change=1.0, market_change=1.0):
    idx = IndexSnapshot(
        code="NIFTY50", value=20000, change=market_change * 200,
        change_pct=market_change, timestamp=NOW, source="test",
    )
    return build_context(stock_change, idx, None)


def test_momentum_detector_fires_on_strong_confirmed_move():
    snap = _snapshot(price_change_pct=3.0, relative_volume=2.0, rsi_14=65.0)
    ctx = _market_context(stock_change=3.0, market_change=1.0)
    pattern = MomentumDetector().detect(INSTRUMENT, snap, ctx, NOW)
    assert pattern is not None
    assert pattern.confirmed is True
    assert len(pattern.supporting_evidence) >= 3


def test_momentum_detector_does_not_fire_on_weak_move():
    snap = _snapshot(price_change_pct=0.5, relative_volume=1.0, rsi_14=50.0)
    ctx = _market_context()
    assert MomentumDetector().detect(INSTRUMENT, snap, ctx, NOW) is None


def test_momentum_detector_rejects_overextended_rsi():
    snap = _snapshot(price_change_pct=3.0, relative_volume=2.0, rsi_14=95.0)
    ctx = _market_context()
    assert MomentumDetector().detect(INSTRUMENT, snap, ctx, NOW) is None


def test_breakout_detector_flags_low_volume_confirmation_risk():
    snap = _snapshot(breakout_distance_pct=1.0, relative_volume=0.8)
    ctx = _market_context()
    pattern = BreakoutDetector().detect(INSTRUMENT, snap, ctx, NOW)
    assert pattern is not None
    assert pattern.confirmed is False
    assert any("false-breakout risk" in e for e in pattern.supporting_evidence)


def test_breakout_detector_confirmed_with_volume_and_market():
    snap = _snapshot(breakout_distance_pct=1.0, relative_volume=2.0)
    ctx = _market_context(stock_change=2.0, market_change=1.0)
    pattern = BreakoutDetector().detect(INSTRUMENT, snap, ctx, NOW)
    assert pattern is not None
    assert pattern.confirmed is True


def test_breakout_detector_no_fire_below_resistance():
    snap = _snapshot(breakout_distance_pct=-1.0)
    ctx = _market_context()
    assert BreakoutDetector().detect(INSTRUMENT, snap, ctx, NOW) is None


def test_pullback_detector_fires_in_retracement_zone_with_light_volume():
    snap = _snapshot(sma_20=145.0, sma_50=140.0, distance_from_sma20_pct=-2.0, relative_volume=0.7)
    ctx = _market_context()
    pattern = PullbackDetector().detect(INSTRUMENT, snap, ctx, NOW)
    assert pattern is not None
    assert pattern.confirmed is True


def test_pullback_detector_no_fire_without_established_trend():
    snap = _snapshot(sma_20=140.0, sma_50=140.0, distance_from_sma20_pct=-2.0)
    ctx = _market_context()
    assert PullbackDetector().detect(INSTRUMENT, snap, ctx, NOW) is None


def test_pullback_detector_no_fire_outside_retracement_zone():
    snap = _snapshot(sma_20=145.0, sma_50=140.0, distance_from_sma20_pct=5.0)
    ctx = _market_context()
    assert PullbackDetector().detect(INSTRUMENT, snap, ctx, NOW) is None


def test_pattern_engine_runs_all_registered_detectors():
    engine = PatternEngine([MomentumDetector(), BreakoutDetector(), PullbackDetector()])
    snap = _snapshot(
        price_change_pct=3.0, relative_volume=2.0, rsi_14=65.0, breakout_distance_pct=1.0,
    )
    ctx = _market_context(stock_change=3.0, market_change=1.0)
    results = engine.run(INSTRUMENT, snap, ctx, NOW)
    families = {p.family.value for p in results}
    assert "MOMENTUM" in families
    assert "BREAKOUT" in families


def test_detected_pattern_requires_evidence():
    from app.domain.patterns import DetectedPattern, PatternFamily

    with pytest.raises(ValueError):
        DetectedPattern(
            family=PatternFamily.MOMENTUM,
            instrument=INSTRUMENT,
            timestamp=NOW,
            supporting_evidence=[],
        )
