"""Candidate Discovery Engine — docs §20.

Pipeline: universe -> liquidity/price/data-quality filter -> pattern/event detection
-> evidence aggregation -> candidate list. Every candidate answers "why did this
appear?" via CandidateEvidence's required reasons — never a bare score.

This does not decide what to do with candidates (alert, rank, ignore) — that's
opportunity/ranking/ and the caller's job. It only answers "is this worth a second
look, and why."
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.domain.market import CandidateEvidence, IndexSnapshot, Instrument, VolumeStatistics
from data.providers.yfinance_provider import YFinanceHistoricalProvider
from market.analytics.context import build_context
from market.analytics.price_volume import build_snapshot
from market.strategies.profile import StrategyProfile
from market.universe.selection import UniverseCandidateStats, is_in_universe
from patterns.breakout.detector import BreakoutDetector
from patterns.engine.base import PatternEngine
from patterns.engine.events import detect_all_events
from patterns.momentum.detector import MomentumDetector
from patterns.pullback.detector import PullbackDetector
from app.config.settings import MarketSettings


@dataclass
class DiscoveryStats:
    scanned: int = 0
    insufficient_history: int = 0
    failed_universe_filter: int = 0
    fetch_errors: int = 0
    candidates_found: int = 0


@dataclass
class DiscoveryResult:
    candidates: list[CandidateEvidence] = field(default_factory=list)
    stats: DiscoveryStats = field(default_factory=DiscoveryStats)


def _build_pattern_engine(profile: StrategyProfile) -> PatternEngine:
    return PatternEngine(
        [
            MomentumDetector(profile.momentum_thresholds),
            BreakoutDetector(profile.breakout_thresholds),
            PullbackDetector(profile.pullback_thresholds),
        ]
    )


class CandidateDiscoveryEngine:
    def __init__(
        self,
        historical_provider: YFinanceHistoricalProvider,
        market_settings: MarketSettings,
    ) -> None:
        self._historical_provider = historical_provider
        self._market_settings = market_settings

    async def discover(
        self,
        instruments: list[Instrument],
        profile: StrategyProfile,
        market_index: IndexSnapshot,
        as_of: datetime,
        start: datetime,
        min_bars: int = 20,
        max_instruments: int | None = None,
    ) -> DiscoveryResult:
        result = DiscoveryResult()
        pattern_engine = _build_pattern_engine(profile)
        scan_list = instruments[:max_instruments] if max_instruments else instruments

        for instrument in scan_list:
            result.stats.scanned += 1
            try:
                bars = await self._historical_provider.get_bars(
                    instrument, profile.bar_interval, start, as_of
                )
            except Exception:  # noqa: BLE001 — one bad symbol shouldn't stop the scan
                result.stats.fetch_errors += 1
                continue

            if len(bars) < min_bars:
                result.stats.insufficient_history += 1
                continue

            closes = [b.close for b in bars]
            volumes = [b.volume for b in bars]
            avg_price = sum(closes) / len(closes)
            avg_volume = sum(volumes) / len(volumes)
            stats = UniverseCandidateStats(
                instrument=instrument,
                last_price=closes[-1],
                avg_traded_value=avg_price * avg_volume,
                history_days_available=len(bars),
                is_sme=False,  # NSE main-board list (data/providers/nse_universe_provider.py)
                has_reliable_data=all(b.close > 0 for b in bars),
            )
            if not is_in_universe(stats, self._market_settings):
                result.stats.failed_universe_filter += 1
                continue

            volume_stats = VolumeStatistics(
                instrument=instrument,
                avg_volume=avg_volume,
                relative_volume=(volumes[-1] / avg_volume) if avg_volume else 0.0,
                volume_acceleration=1.0,
                as_of=as_of,
            )
            snapshot = build_snapshot(bars, volume_stats)
            context = build_context(snapshot.price_change_pct or 0.0, market_index, None)

            patterns = pattern_engine.run(instrument, snapshot, context, as_of)
            events = detect_all_events(instrument, snapshot, context, as_of)

            if not patterns and not events:
                continue

            reasons = [f"{p.family.value}: {e}" for p in patterns for e in p.supporting_evidence]
            reasons += [f"{ev.category.value} event: {ev.description}" for ev in events]
            risks = [
                f"{p.family.value} pattern not confirmed by volume/market"
                for p in patterns
                if not p.confirmed
            ]

            result.candidates.append(
                CandidateEvidence(
                    instrument=instrument,
                    generated_at=as_of,
                    reasons=reasons,
                    risks=risks,
                )
            )
            result.stats.candidates_found += 1

        return result
