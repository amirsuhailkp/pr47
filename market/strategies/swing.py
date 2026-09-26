"""Swing strategy — multi-day holds on daily bars, waiting for a stronger, more
confirmed move than scalping requires. This is the profile the pipeline used by
default before strategy profiles existed (docs/PROJECT_PLAN.md §24: a hypothesis to
test, not a claim of profitability).
"""
from __future__ import annotations

from app.domain.patterns import Severity
from app.domain.strategy import StrategyDefinition
from market.strategies.profile import StrategyProfile
from patterns.breakout.detector import BreakoutThresholds
from patterns.momentum.detector import MomentumThresholds
from patterns.pullback.detector import PullbackThresholds

SWING_DEFINITION = StrategyDefinition(
    name="Swing — daily momentum/breakout/pullback",
    hypothesis=(
        "A daily close showing a meaningfully large, volume-confirmed move, or a "
        "shallow pullback within an established uptrend, tends to see continuation "
        "over the next several trading days."
    ),
    setup_conditions=(
        "Price change >= 2.0% on the daily bar with relative volume >= 1.5x recent "
        "average and RSI(14) between 55-85 (MOMENTUM); price clearing the prior "
        "20-day high (BREAKOUT); or a retracement of 1-8% below a rising 20-day "
        "average within an established uptrend on light volume (PULLBACK)."
    ),
    confirmation=(
        "NIFTY moving in the same direction on the same day; for breakout, relative "
        "volume >= 1.5x confirming the move rather than a thin, easily-reversed break."
    ),
    invalidation=(
        "Price closes back below the breakout level, the pullback deepens past the "
        "trend-break threshold, or the broader market/sector reverses against the "
        "setup on materially higher volume."
    ),
    timeframe="Daily bars, positions typically held 3-20 trading days",
    required_data=(
        "Daily OHLCV bars, at least 50 trading days of history for the moving-average "
        "and RSI calculations to be meaningful. yfinance's free daily data is "
        "sufficient for this timeframe (unlike scalping's intraday requirement)."
    ),
    costs_and_slippage_notes=(
        "Brokerage/STT/slippage are proportionally small at this holding period but "
        "are still not modeled in any backtest run against this profile yet — "
        "history/backtest/ produces gross, not net, returns."
    ),
    liquidity_assumptions=(
        "Assumes market/universe/selection.py's liquidity filter (min average traded "
        "value) has already excluded instruments too thin to enter/exit a multi-day "
        "position without moving the price."
    ),
    limitations=(
        "Thresholds are hand-set defaults, not fit to Indian-market history yet — "
        "run this profile through history/backtest/ (chronological validation, "
        "leakage checks) before treating its signals as anything more than a "
        "starting hypothesis to investigate."
    ),
)

SWING_PROFILE = StrategyProfile(
    definition=SWING_DEFINITION,
    bar_interval="1d",
    lookback_days=180,
    momentum_thresholds=MomentumThresholds(),  # codebase defaults, already daily-tuned
    breakout_thresholds=BreakoutThresholds(),
    pullback_thresholds=PullbackThresholds(),
    alert_cooldown_seconds=14400,  # 4 hours — don't re-alert the same setup same session
    min_alert_severity=Severity.WATCH,
)
