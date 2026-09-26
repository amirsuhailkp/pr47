"""Configurable universe selection.

Price bounds and liquidity thresholds come from Settings.market, never hard-coded here.
The price band is not itself a safety definition — liquidity and data-quality filters
matter as much as price.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config.settings import MarketSettings
from app.domain.market import Instrument


@dataclass(frozen=True)
class UniverseCandidateStats:
    instrument: Instrument
    last_price: float
    avg_traded_value: float
    history_days_available: int
    is_sme: bool
    has_reliable_data: bool


def is_in_universe(stats: UniverseCandidateStats, settings: MarketSettings) -> bool:
    if settings.exclude_sme and stats.is_sme:
        return False
    if not stats.has_reliable_data:
        return False
    if stats.history_days_available < settings.min_history_days:
        return False
    if not (settings.min_price <= stats.last_price <= settings.max_price):
        return False
    if stats.avg_traded_value < settings.min_avg_traded_value:
        return False
    return True


def filter_universe(
    candidates: list[UniverseCandidateStats], settings: MarketSettings
) -> list[Instrument]:
    return [c.instrument for c in candidates if is_in_universe(c, settings)]
