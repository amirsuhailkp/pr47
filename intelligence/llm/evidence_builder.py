"""Assembles StructuredEvidence from already-computed analytics/pattern/history
objects. This module only converts and copies fields — it never invents or infers
new facts, since everything the LLM sees must trace back to deterministic code.
"""
from __future__ import annotations

from app.domain.history import HistoricalSummary
from app.domain.llm import StructuredEvidence
from app.domain.market import Instrument
from app.domain.patterns import DetectedPattern
from market.analytics.context import MarketContext
from market.analytics.price_volume import PriceVolumeSnapshot


def _pattern_to_dict(pattern: DetectedPattern) -> dict:
    return {
        "family": pattern.family.value,
        "confirmed": pattern.confirmed,
        "evidence": list(pattern.supporting_evidence),
        "market_context_note": pattern.market_context_note,
        "sector_context_note": pattern.sector_context_note,
    }


def _historical_summary_to_dict(summary: HistoricalSummary) -> dict:
    return {
        "setup_criteria": summary.setup_criteria,
        "sample_size": summary.sample_size,
        "horizons": {
            h: {
                "sample_size": hs.sample_size,
                "median_return_pct": hs.median_return_pct,
                "mean_return_pct": hs.mean_return_pct,
                "positive_frequency": hs.positive_frequency,
                "negative_frequency": hs.negative_frequency,
                "uncertainty_note": hs.uncertainty_note,
            }
            for h, hs in summary.horizons.items()
        },
    }


def build_evidence(
    instrument: Instrument,
    snapshot: PriceVolumeSnapshot,
    context: MarketContext,
    patterns: list[DetectedPattern],
    historical_summary: HistoricalSummary | None = None,
    news: list[dict] | None = None,
    risk_flags: list[str] | None = None,
) -> StructuredEvidence:
    market_context = {
        "market_change_pct": context.market_index.change_pct,
        "relative_strength_vs_market": context.relative_strength_vs_market,
        "market_confirms_move": context.market_confirms_move,
        "regime": context.regime.value,
    }
    sector_context = None
    if context.sector_index is not None:
        sector_context = {
            "sector_change_pct": context.sector_index.change_pct,
            "relative_strength_vs_sector": context.relative_strength_vs_sector,
            "sector_confirms_move": context.sector_confirms_move,
        }

    return StructuredEvidence(
        instrument_symbol=instrument.symbol,
        price=snapshot.price,
        price_change_pct=snapshot.price_change_pct,
        relative_volume=snapshot.relative_volume,
        rsi_14=snapshot.rsi_14,
        vwap=snapshot.vwap,
        market_context=market_context,
        sector_context=sector_context,
        detected_patterns=[_pattern_to_dict(p) for p in patterns],
        historical_cases=(
            _historical_summary_to_dict(historical_summary) if historical_summary else None
        ),
        news=news or [],
        risk_flags=risk_flags or [],
    )
