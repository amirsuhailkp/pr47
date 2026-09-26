from datetime import datetime, timezone

from app.domain.history import HistoricalSummary, HorizonSummary
from app.domain.market import IndexSnapshot, Instrument
from app.domain.patterns import DetectedPattern, PatternFamily
from intelligence.llm.evidence_builder import build_evidence
from market.analytics.context import build_context
from market.analytics.price_volume import PriceVolumeSnapshot

NOW = datetime.now(timezone.utc)
INSTRUMENT = Instrument(symbol="XYZ", exchange="NSE")


def _snapshot() -> PriceVolumeSnapshot:
    return PriceVolumeSnapshot(
        price=184.6, price_change_pct=4.72, relative_volume=3.4, volume_acceleration=2.0,
        rsi_14=68.0, atr_14=2.0, sma_20=180.0, sma_50=170.0, ema_20=181.0, vwap=182.0,
        distance_from_vwap_pct=1.4, distance_from_sma20_pct=2.5, recent_high_20=183.0,
        recent_low_20=160.0, breakout_distance_pct=0.9, drawdown_pct=-0.5,
    )


def test_build_evidence_includes_market_and_pattern_context():
    idx = IndexSnapshot(code="NIFTY50", value=20000, change=180, change_pct=0.9, timestamp=NOW, source="test")
    ctx = build_context(4.72, idx, None)
    pattern = DetectedPattern(
        family=PatternFamily.MOMENTUM, instrument=INSTRUMENT, timestamp=NOW,
        supporting_evidence=["price_change_pct=4.72"], confirmed=True,
    )
    evidence = build_evidence(INSTRUMENT, _snapshot(), ctx, [pattern])
    payload = evidence.to_payload()

    assert payload["instrument_symbol"] == "XYZ"
    assert payload["price"] == 184.6
    assert payload["market_context"]["market_confirms_move"] is True
    assert payload["detected_patterns"][0]["family"] == "MOMENTUM"
    assert payload["sector_context"] is None
    assert payload["historical_cases"] is None


def test_build_evidence_includes_historical_summary_without_collapsing_it():
    idx = IndexSnapshot(code="NIFTY50", value=20000, change=180, change_pct=0.9, timestamp=NOW, source="test")
    ctx = build_context(4.72, idx, None)
    horizon = HorizonSummary(
        horizon="5d", sample_size=127, median_return_pct=2.1, mean_return_pct=1.8,
        positive_frequency=0.6, negative_frequency=0.4, return_distribution=(1.0, 2.0),
        mean_max_favorable_excursion_pct=3.0, mean_max_adverse_excursion_pct=-1.0,
        return_volatility=1.5, regime_breakdown={"RISK_ON": 100}, uncertainty_note="",
    )
    summary = HistoricalSummary(setup_criteria="momentum breakout", sample_size=127, horizons={"5d": horizon})

    evidence = build_evidence(INSTRUMENT, _snapshot(), ctx, [], historical_summary=summary)
    payload = evidence.to_payload()
    assert payload["historical_cases"]["sample_size"] == 127
    assert payload["historical_cases"]["horizons"]["5d"]["positive_frequency"] == 0.6
