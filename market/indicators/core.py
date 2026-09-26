"""Deterministic technical indicators.

Every function is pure: given the same bars/closes it always returns the same result,
so these are safe to unit test and safe to feed into historical/backtest code without
any risk of look-ahead leakage (no function here looks past the data it's given).
"""
from __future__ import annotations

import math

from app.domain.market import OHLCVBar


def sma(values: list[float], period: int) -> float | None:
    if len(values) < period or period <= 0:
        return None
    return sum(values[-period:]) / period


def ema_series(values: list[float], period: int) -> list[float]:
    """Full EMA series (index-aligned with `values`). Empty if not enough data."""
    if len(values) < period or period <= 0:
        return []
    k = 2 / (period + 1)
    out = [sum(values[:period]) / period]  # seed with SMA
    for v in values[period:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def ema(values: list[float], period: int) -> float | None:
    series = ema_series(values, period)
    return series[-1] if series else None


def rolling_return(values: list[float], period: int) -> float | None:
    """Percent return over the last `period` bars."""
    if len(values) <= period or period <= 0:
        return None
    start = values[-(period + 1)]
    end = values[-1]
    if start == 0:
        return None
    return (end - start) / start * 100.0


def volatility(returns: list[float]) -> float | None:
    """Standard deviation of a list of period returns (e.g. daily % changes)."""
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(variance)


def true_range(bar: OHLCVBar, prev_close: float | None) -> float:
    if prev_close is None:
        return bar.high - bar.low
    return max(
        bar.high - bar.low,
        abs(bar.high - prev_close),
        abs(bar.low - prev_close),
    )


def atr(bars: list[OHLCVBar], period: int = 14) -> float | None:
    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        trs.append(true_range(bars[i], bars[i - 1].close))
    if len(trs) < period:
        return None
    return sma(trs, period)


def rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1 + rs))


def vwap(bars: list[OHLCVBar]) -> float | None:
    """Session VWAP — pass only the bars belonging to the session being measured."""
    if not bars:
        return None
    total_pv = 0.0
    total_v = 0
    for b in bars:
        typical_price = (b.high + b.low + b.close) / 3
        total_pv += typical_price * b.volume
        total_v += b.volume
    if total_v == 0:
        return None
    return total_pv / total_v


def distance_from_vwap_pct(price: float, vwap_value: float | None) -> float | None:
    if vwap_value is None or vwap_value == 0:
        return None
    return (price - vwap_value) / vwap_value * 100.0


def distance_from_ma_pct(price: float, ma_value: float | None) -> float | None:
    if ma_value is None or ma_value == 0:
        return None
    return (price - ma_value) / ma_value * 100.0


def recent_high(bars: list[OHLCVBar], lookback: int) -> float | None:
    window = bars[-lookback:]
    if not window:
        return None
    return max(b.high for b in window)


def recent_low(bars: list[OHLCVBar], lookback: int) -> float | None:
    window = bars[-lookback:]
    if not window:
        return None
    return min(b.low for b in window)


def breakout_distance_pct(price: float, resistance: float | None) -> float | None:
    """Positive = price above resistance; negative = price still below it."""
    if resistance is None or resistance == 0:
        return None
    return (price - resistance) / resistance * 100.0


def drawdown_pct(values: list[float]) -> float | None:
    """Drawdown of the last value from the running peak within the given window."""
    if not values:
        return None
    peak = max(values)
    if peak == 0:
        return None
    return (values[-1] - peak) / peak * 100.0
