"""Price and volume analytics for a single instrument.

Combines the pure indicator primitives (market/indicators/core.py) into the handful
of derived measures the pattern detectors and alert engine actually consume. Every
function here takes explicit inputs and returns a value or None — no hidden state,
no network calls, no side effects. Reasons for using each measure are documented
inline since docs/PROJECT_PLAN.md requires "every feature must have a clear reason".
"""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.market import OHLCVBar, VolumeStatistics
from market.indicators import core


@dataclass(frozen=True)
class PriceVolumeSnapshot:
    """A point-in-time analytics snapshot for one instrument.

    This is the object fed to pattern detectors and, eventually, to LLM evidence
    payloads — see docs/LLM_ARCHITECTURE.md (structured evidence, not raw prompts).
    """

    price: float
    price_change_pct: float | None
    relative_volume: float | None
    volume_acceleration: float | None
    rsi_14: float | None
    atr_14: float | None
    sma_20: float | None
    sma_50: float | None
    ema_20: float | None
    vwap: float | None
    distance_from_vwap_pct: float | None
    distance_from_sma20_pct: float | None
    recent_high_20: float | None
    recent_low_20: float | None
    breakout_distance_pct: float | None
    drawdown_pct: float | None


def price_change_pct(bars: list[OHLCVBar]) -> float | None:
    """Change vs the previous completed bar's close — the simplest "what changed" signal."""
    if len(bars) < 2:
        return None
    prev_close = bars[-2].close
    if prev_close == 0:
        return None
    return (bars[-1].close - prev_close) / prev_close * 100.0


def relative_volume(current_volume: int, avg_volume: float | None) -> float | None:
    """Current volume vs its own historical average — flags unusual activity
    independent of the stock's normal liquidity level."""
    if not avg_volume:
        return None
    return current_volume / avg_volume


def volume_acceleration(recent_volumes: list[int], lookback: int = 5) -> float | None:
    """Ratio of the most recent bar's volume to the average of the preceding window —
    catches volume that is not just elevated but actively accelerating."""
    if len(recent_volumes) < lookback + 1:
        return None
    window = recent_volumes[-(lookback + 1):-1]
    avg = sum(window) / len(window)
    if avg == 0:
        return None
    return recent_volumes[-1] / avg


def build_snapshot(
    bars: list[OHLCVBar], volume_stats: VolumeStatistics | None = None
) -> PriceVolumeSnapshot:
    """Assemble a full analytics snapshot from a bar history (most recent bar last)."""
    if not bars:
        raise ValueError("build_snapshot requires at least one bar")

    closes = [b.close for b in bars]
    price = closes[-1]
    rel_vol = None
    vol_accel = volume_acceleration([b.volume for b in bars])
    if volume_stats is not None:
        rel_vol = volume_stats.relative_volume

    sma20 = core.sma(closes, 20)
    sma50 = core.sma(closes, 50)
    ema20 = core.ema(closes, 20)
    vwap_value = core.vwap(bars)
    # Resistance/support are measured from bars *before* the current one — otherwise
    # the current bar's own high/low would trivially set the level being tested against it.
    prior_bars = bars[:-1]
    recent_high20 = core.recent_high(prior_bars, 20)
    recent_low20 = core.recent_low(prior_bars, 20)

    return PriceVolumeSnapshot(
        price=price,
        price_change_pct=price_change_pct(bars),
        relative_volume=rel_vol,
        volume_acceleration=vol_accel,
        rsi_14=core.rsi(closes, 14),
        atr_14=core.atr(bars, 14),
        sma_20=sma20,
        sma_50=sma50,
        ema_20=ema20,
        vwap=vwap_value,
        distance_from_vwap_pct=core.distance_from_vwap_pct(price, vwap_value),
        distance_from_sma20_pct=core.distance_from_ma_pct(price, sma20),
        recent_high_20=recent_high20,
        recent_low_20=recent_low20,
        breakout_distance_pct=core.breakout_distance_pct(price, recent_high20),
        drawdown_pct=core.drawdown_pct(closes[-20:]),
    )
