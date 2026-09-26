"""Computes OutcomeRecords for a HistoricalSetup from its forward price path.

Only ever consumes bars strictly after the setup's timestamp — this is the leakage
boundary. See history/backtest/leakage_tests.py for the automated checks on this.
"""
from __future__ import annotations

from app.domain.history import HistoricalSetup, OutcomeRecord
from app.domain.market import OHLCVBar

# Horizon -> number of forward bars, for a caller-defined bar interval (e.g. daily bars
# for the day-based horizons). Intraday horizons need intraday bars supplied separately.
HORIZON_BAR_COUNTS: dict[str, int] = {
    "1d": 1,
    "3d": 3,
    "5d": 5,
    "10d": 10,
    "20d": 20,
}


def compute_outcome(
    setup: HistoricalSetup,
    forward_bars: list[OHLCVBar],
    horizon: str,
    market_regime_at_horizon: str | None = None,
) -> OutcomeRecord | None:
    """`forward_bars` must be strictly after setup.timestamp, ordered ascending, and
    must not include the setup bar itself. Returns None if there isn't enough forward
    data yet for this horizon — that is a valid, expected result, not an error."""
    n = HORIZON_BAR_COUNTS.get(horizon)
    if n is None:
        raise ValueError(f"unknown horizon: {horizon}")
    if len(forward_bars) < n:
        return None

    window = forward_bars[:n]
    for bar in window:
        if bar.timestamp <= setup.timestamp:
            raise ValueError(
                "forward_bars must be strictly after the setup timestamp — "
                "using same-or-earlier bars would leak information"
            )

    entry_price = setup.price
    exit_price = window[-1].close
    return_pct = (exit_price - entry_price) / entry_price * 100.0 if entry_price else 0.0

    highs = [b.high for b in window]
    lows = [b.low for b in window]
    mfe = (max(highs) - entry_price) / entry_price * 100.0 if entry_price else 0.0
    mae = (min(lows) - entry_price) / entry_price * 100.0 if entry_price else 0.0

    closes = [entry_price] + [b.close for b in window]
    period_returns = [
        (closes[i] - closes[i - 1]) / closes[i - 1] * 100.0
        for i in range(1, len(closes))
        if closes[i - 1] != 0
    ]
    realized_vol = None
    if len(period_returns) >= 2:
        mean = sum(period_returns) / len(period_returns)
        variance = sum((r - mean) ** 2 for r in period_returns) / (len(period_returns) - 1)
        realized_vol = variance ** 0.5

    return OutcomeRecord(
        setup=setup,
        horizon=horizon,
        return_pct=return_pct,
        max_favorable_excursion_pct=mfe,
        max_adverse_excursion_pct=mae,
        realized_volatility=realized_vol,
        market_regime_at_horizon=market_regime_at_horizon,
    )
