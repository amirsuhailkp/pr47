"""Breakout pattern — price clearing recent resistance with volume confirmation.

Also flags a possible false-breakout risk when volume doesn't confirm, since the spec
explicitly calls out "potential false breakout" as part of what this pattern should
surface (docs/PROJECT_PLAN.md §13).
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
class BreakoutThresholds:
    min_breakout_distance_pct: float = 0.3
    confirming_relative_volume: float = 1.5


class BreakoutDetector(PatternDetector):
    family_name = "BREAKOUT"

    def __init__(self, thresholds: BreakoutThresholds = BreakoutThresholds()) -> None:
        self._t = thresholds

    def detect(
        self,
        instrument: Instrument,
        snapshot: PriceVolumeSnapshot,
        context: MarketContext,
        as_of: datetime,
    ) -> DetectedPattern | None:
        bd = snapshot.breakout_distance_pct
        if bd is None or bd < self._t.min_breakout_distance_pct:
            return None

        rel_vol = snapshot.relative_volume
        volume_confirms = rel_vol is not None and rel_vol >= self._t.confirming_relative_volume

        evidence = [
            f"breakout_distance_pct={bd:.2f} (>= {self._t.min_breakout_distance_pct})",
            f"recent_high_20={snapshot.recent_high_20}",
            f"price={snapshot.price}",
        ]
        if rel_vol is not None:
            evidence.append(f"relative_volume={rel_vol:.2f}x")
        if not volume_confirms:
            evidence.append("volume_confirmation=NO — elevated false-breakout risk")

        return DetectedPattern(
            family=PatternFamily.BREAKOUT,
            instrument=instrument,
            timestamp=as_of,
            supporting_evidence=evidence,
            confirmed=volume_confirms and context.market_confirms_move,
            market_context_note=(
                "market confirms" if context.market_confirms_move else "market does not confirm"
            ),
            sector_context_note=(
                None
                if context.sector_confirms_move is None
                else ("sector confirms" if context.sector_confirms_move else "sector does not confirm")
            ),
        )
