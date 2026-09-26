from datetime import datetime, timezone

from app.domain.market import IndexSnapshot
from market.analytics.context import MarketRegime, build_context, classify_regime


def _index(code: str, change_pct: float) -> IndexSnapshot:
    return IndexSnapshot(
        code=code,
        value=20000.0,
        change=change_pct * 200,
        change_pct=change_pct,
        timestamp=datetime.now(timezone.utc),
        source="test",
    )


def test_relative_strength_vs_market():
    ctx = build_context(5.0, _index("NIFTY50", 2.0), None)
    assert ctx.relative_strength_vs_market == 3.0


def test_market_confirms_move_same_direction():
    ctx = build_context(5.0, _index("NIFTY50", 1.0), None)
    assert ctx.market_confirms_move is True

    ctx2 = build_context(5.0, _index("NIFTY50", -1.0), None)
    assert ctx2.market_confirms_move is False


def test_sector_confirmation_requires_sector_index():
    ctx = build_context(5.0, _index("NIFTY50", 1.0), None)
    assert ctx.sector_confirms_move is None
    assert ctx.relative_strength_vs_sector is None

    ctx2 = build_context(5.0, _index("NIFTY50", 1.0), _index("NIFTY_IT", -1.0))
    assert ctx2.sector_confirms_move is False
    assert ctx2.relative_strength_vs_sector == 6.0


def test_classify_regime_high_volatility_overrides_direction():
    assert classify_regime(2.0, market_volatility=2.0, vol_threshold=1.5) == MarketRegime.HIGH_VOLATILITY


def test_classify_regime_risk_on_off_neutral():
    assert classify_regime(1.0, None) == MarketRegime.RISK_ON
    assert classify_regime(-1.0, None) == MarketRegime.RISK_OFF
    assert classify_regime(0.1, None) == MarketRegime.NEUTRAL
