"""Scalping strategy — many small, fast setups on intraday bars, exited quickly.

Deliberately tighter thresholds than swing: a scalp doesn't wait for a 2% move to
confirm, because by then the trade this style is built around has already passed.
This is a hypothesis to test against history (docs §24), not a claim it's profitable.
"""
from __future__ import annotations

from app.domain.patterns import Severity
from app.domain.strategy import StrategyDefinition
from market.strategies.profile import StrategyProfile
from patterns.breakout.detector import BreakoutThresholds
from patterns.momentum.detector import MomentumThresholds
from patterns.pullback.detector import PullbackThresholds

SCALPING_DEFINITION = StrategyDefinition(
    name="Scalping — intraday momentum/breakout",
    hypothesis=(
        "Small, fast relative-volume-confirmed price moves on 5-minute bars tend to "
        "extend for a few more bars before mean-reverting, offering a brief window "
        "for a quick in-and-out trade."
    ),
    setup_conditions=(
        "Price change >= 0.3% on the current 5-minute bar with relative volume >= "
        "1.2x recent average, OR price breaking the prior 20-bar high/low by any "
        "positive margin."
    ),
    confirmation=(
        "Market (NIFTY) moving in the same direction on the same bar; relative "
        "volume clearing the breakout threshold for BREAKOUT patterns specifically."
    ),
    invalidation=(
        "Price reverses back through the entry level within the next 1-3 bars, or "
        "relative volume collapses back below 1.0x — both suggest the move was noise, "
        "not a real intraday shift."
    ),
    timeframe="5-minute bars, held for minutes not hours",
    required_data=(
        "Intraday 5-minute OHLCV bars, ideally real-time from a broker feed — "
        "yfinance's 5m data (available for roughly the last 60 days) is a stand-in "
        "for testing, not a substitute for live intraday ticks."
    ),
    costs_and_slippage_notes=(
        "NOT YET MODELED: brokerage, STT, and slippage are material at this "
        "frequency and are not deducted from any backtest run against this profile "
        "yet — a real evaluation must add per-trade cost assumptions before any "
        "historical win rate here is treated as realistic."
    ),
    liquidity_assumptions=(
        "Assumes the instrument's normal 5-minute volume is enough to enter/exit "
        "without materially moving the price — not verified per-instrument by this "
        "profile; that check belongs in market/universe/selection.py liquidity filters."
    ),
    limitations=(
        "Untested against real intraday history in this codebase so far — only "
        "synthetic/manual runs. High sensitivity to data-feed latency, which yfinance "
        "and IndianAPI.in (both used for testing) do not provide. Treat any signal "
        "from this profile as a candidate to investigate, never an execution instruction."
    ),
)

SCALPING_PROFILE = StrategyProfile(
    definition=SCALPING_DEFINITION,
    bar_interval="5m",
    lookback_days=5,
    momentum_thresholds=MomentumThresholds(
        min_price_change_pct=0.3, min_relative_volume=1.2, min_rsi=52.0, max_rsi=90.0
    ),
    breakout_thresholds=BreakoutThresholds(
        min_breakout_distance_pct=0.1, confirming_relative_volume=1.2
    ),
    pullback_thresholds=PullbackThresholds(
        trend_sma_gap_pct=0.3,
        max_pullback_from_sma20_pct=-0.2,
        min_pullback_from_sma20_pct=-2.0,
        light_volume_relative=1.0,
    ),
    alert_cooldown_seconds=300,  # 5 minutes — don't re-alert the same setup within one bar or two
    min_alert_severity=Severity.WATCH,
)
