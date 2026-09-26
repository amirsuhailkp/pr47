"""Momentum pattern — price acceleration + relative volume expansion + trend/relative
strength confirmed by market and (where available) sector. Research pattern, not a
claim of profitability (docs/PROJECT_PLAN.md §13).
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
class MomentumThresholds:
    min_price_change_pct: float = 2.0
    min_relative_volume: float = 1.5
    min_rsi: float = 55.0
    max_rsi: float = 85.0  # above this, momentum is extended, not fresh


class MomentumDetector(PatternDetector):
    family_name = "MOMENTUM"

    def __init__(self, thresholds: MomentumThresholds = MomentumThresholds()) -> None:
        self._t = thresholds

    def detect(
        self,
        instrument: Instrument,
        snapshot: PriceVolumeSnapshot,
        context: MarketContext,
        as_of: datetime,
    ) -> DetectedPattern | None:
        change = snapshot.price_change_pct
        rel_vol = snapshot.relative_volume
        rsi = snapshot.rsi_14

        if change is None or rel_vol is None or rsi is None:
            return None
        if change < self._t.min_price_change_pct:
            return None
        if rel_vol < self._t.min_relative_volume:
            return None
        if not (self._t.min_rsi <= rsi <= self._t.max_rsi):
            return None

        evidence = [
            f"price_change_pct={change:.2f} (>= {self._t.min_price_change_pct})",
            f"relative_volume={rel_vol:.2f}x (>= {self._t.min_relative_volume})",
            f"rsi_14={rsi:.1f} (in [{self._t.min_rsi}, {self._t.max_rsi}])",
            f"relative_strength_vs_market={context.relative_strength_vs_market:.2f}",
        ]
        if context.relative_strength_vs_sector is not None:
            evidence.append(
                f"relative_strength_vs_sector={context.relative_strength_vs_sector:.2f}"
            )

        return DetectedPattern(
            family=PatternFamily.MOMENTUM,
            instrument=instrument,
            timestamp=as_of,
            supporting_evidence=evidence,
            confirmed=context.market_confirms_move,
            market_context_note=(
                "market confirms" if context.market_confirms_move else "market does not confirm"
            ),
            sector_context_note=(
                None
                if context.sector_confirms_move is None
                else ("sector confirms" if context.sector_confirms_move else "sector does not confirm")
            ),
        )
