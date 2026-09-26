"""Momentum-pullback pattern — an established uptrend retracing toward support
(VWAP / moving average) on light volume, with signs of recovery/confirmation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.market import Instrument
from app.domain.patterns import DetectedPattern, PatternFamily
from market.analytics.context import MarketContext
from market.analytics.price_volume import PriceVolumeSnapshot
from patterns.engine.base import PatternDetector


@dataclass(frozen=True)
class PullbackThresholds:
    trend_sma_gap_pct: float = 1.0  # sma20 must be at least this far above sma50
    max_pullback_from_sma20_pct: float = -1.0  # price at/below sma20 (negative distance)
    min_pullback_from_sma20_pct: float = -8.0  # but not a full trend break
    light_volume_relative: float = 1.0  # pullback volume should be at/below average


class PullbackDetector(PatternDetector):
    family_name = "PULLBACK"

    def __init__(self, thresholds: PullbackThresholds = PullbackThresholds()) -> None:
        self._t = thresholds

    def detect(
        self,
        instrument: Instrument,
        snapshot: PriceVolumeSnapshot,
        context: MarketContext,
        as_of: datetime,
    ) -> DetectedPattern | None:
        sma20, sma50 = snapshot.sma_20, snapshot.sma_50
        if sma20 is None or sma50 is None:
            return None

        trend_strength_pct = (sma20 - sma50) / sma50 * 100.0 if sma50 else None
        if trend_strength_pct is None or trend_strength_pct < self._t.trend_sma_gap_pct:
            return None  # no established uptrend

        dist = snapshot.distance_from_sma20_pct
        if dist is None:
            return None
        if not (self._t.min_pullback_from_sma20_pct <= dist <= self._t.max_pullback_from_sma20_pct):
            return None  # not in the retracement zone

        rel_vol = snapshot.relative_volume
        light_volume = rel_vol is not None and rel_vol <= self._t.light_volume_relative

        vwap_dist = snapshot.distance_from_vwap_pct

        evidence = [
            f"established_uptrend: sma20 {trend_strength_pct:.2f}% above sma50",
            f"distance_from_sma20_pct={dist:.2f} (retracement zone)",
        ]
        if rel_vol is not None:
            evidence.append(
                f"relative_volume={rel_vol:.2f}x "
                f"({'light — healthy pullback' if light_volume else 'elevated — watch for breakdown'})"
            )
        if vwap_dist is not None:
            evidence.append(f"distance_from_vwap_pct={vwap_dist:.2f}")

        return DetectedPattern(
            family=PatternFamily.PULLBACK,
            instrument=instrument,
            timestamp=as_of,
            supporting_evidence=evidence,
            confirmed=light_volume,
            market_context_note=(
                "market confirms" if context.market_confirms_move else "market does not confirm"
            ),
            sector_context_note=(
                None
                if context.sector_confirms_move is None
                else ("sector confirms" if context.sector_confirms_move else "sector does not confirm")
            ),
        )
