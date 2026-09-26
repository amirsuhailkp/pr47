import pytest

from app.domain.patterns import Severity
from app.domain.strategy import StrategyDefinition
from app.orchestration.pipeline import build_pipeline_from_profile
from market.strategies.registry import STRATEGIES, UnknownStrategyError, get_strategy
from market.strategies.scalping import SCALPING_PROFILE
from market.strategies.swing import SWING_PROFILE


def test_strategy_definition_requires_every_field_nonempty():
    with pytest.raises(ValueError):
        StrategyDefinition(
            name="x", hypothesis="", setup_conditions="x", confirmation="x",
            invalidation="x", timeframe="x", required_data="x",
            costs_and_slippage_notes="x", liquidity_assumptions="x", limitations="x",
        )


def test_strategy_definition_as_text_includes_all_sections():
    text = SWING_PROFILE.definition.as_text()
    for section in ("Hypothesis", "Setup", "Confirmation", "Invalidation", "Limitations"):
        assert section in text


def test_scalping_and_swing_have_distinct_timeframes_and_thresholds():
    assert SCALPING_PROFILE.bar_interval == "5m"
    assert SWING_PROFILE.bar_interval == "1d"
    assert (
        SCALPING_PROFILE.momentum_thresholds.min_price_change_pct
        < SWING_PROFILE.momentum_thresholds.min_price_change_pct
    )
    assert SCALPING_PROFILE.alert_cooldown_seconds < SWING_PROFILE.alert_cooldown_seconds


def test_registry_lookup_case_insensitive():
    assert get_strategy("SCALPING") is SCALPING_PROFILE
    assert get_strategy("swing") is SWING_PROFILE


def test_registry_unknown_strategy_raises():
    with pytest.raises(UnknownStrategyError):
        get_strategy("nonexistent")


def test_registry_contains_exactly_scalping_and_swing():
    assert set(STRATEGIES.keys()) == {"scalping", "swing"}


def test_build_pipeline_from_profile_uses_profile_thresholds():
    pipeline = build_pipeline_from_profile(SCALPING_PROFILE)
    # the pattern engine's momentum detector should carry the scalping thresholds
    momentum_detector = pipeline.pattern_engine._detectors[0]
    assert momentum_detector._t.min_price_change_pct == 0.3
    assert pipeline.alert_engine._min_severity == Severity.WATCH
