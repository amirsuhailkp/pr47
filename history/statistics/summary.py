"""Builds HorizonSummary / HistoricalSummary from OutcomeRecords.

docs §21: "Do NOT reduce historical evidence to a single prediction percentage." Every
summary carries sample size, a full distribution, and an explicit uncertainty note when
the sample is thin.
"""
from __future__ import annotations

import statistics as pystats

from app.domain.history import HistoricalSummary, HorizonSummary, OutcomeRecord

SMALL_SAMPLE_THRESHOLD = 30


def _uncertainty_note(sample_size: int) -> str:
    if sample_size == 0:
        return "No historical cases found — insufficient evidence."
    if sample_size < SMALL_SAMPLE_THRESHOLD:
        return (
            f"Small sample size (n={sample_size}) — treat this distribution as "
            "indicative only, not reliable evidence."
        )
    return ""


def summarize_horizon(horizon: str, outcomes: list[OutcomeRecord]) -> HorizonSummary:
    n = len(outcomes)
    if n == 0:
        return HorizonSummary(
            horizon=horizon,
            sample_size=0,
            median_return_pct=None,
            mean_return_pct=None,
            positive_frequency=None,
            negative_frequency=None,
            return_distribution=(),
            mean_max_favorable_excursion_pct=None,
            mean_max_adverse_excursion_pct=None,
            return_volatility=None,
            regime_breakdown={},
            uncertainty_note=_uncertainty_note(0),
        )

    returns = sorted(o.return_pct for o in outcomes)
    positive = sum(1 for r in returns if r > 0)
    negative = sum(1 for r in returns if r < 0)

    regime_breakdown: dict[str, int] = {}
    for o in outcomes:
        key = o.market_regime_at_horizon or "UNKNOWN"
        regime_breakdown[key] = regime_breakdown.get(key, 0) + 1

    return HorizonSummary(
        horizon=horizon,
        sample_size=n,
        median_return_pct=pystats.median(returns),
        mean_return_pct=sum(returns) / n,
        positive_frequency=positive / n,
        negative_frequency=negative / n,
        return_distribution=tuple(returns),
        mean_max_favorable_excursion_pct=sum(o.max_favorable_excursion_pct for o in outcomes) / n,
        mean_max_adverse_excursion_pct=sum(o.max_adverse_excursion_pct for o in outcomes) / n,
        return_volatility=pystats.pstdev(returns) if n >= 2 else None,
        regime_breakdown=regime_breakdown,
        uncertainty_note=_uncertainty_note(n),
    )


def summarize(
    setup_criteria: str, outcomes_by_horizon: dict[str, list[OutcomeRecord]]
) -> HistoricalSummary:
    horizons = {h: summarize_horizon(h, outs) for h, outs in outcomes_by_horizon.items()}
    total_sample = max((s.sample_size for s in horizons.values()), default=0)
    return HistoricalSummary(
        setup_criteria=setup_criteria, sample_size=total_sample, horizons=horizons
    )


def percentile(sorted_returns: tuple[float, ...], pct: float) -> float | None:
    """Simple percentile lookup for a returns distribution, e.g. percentile(dist, 10)."""
    if not sorted_returns:
        return None
    if len(sorted_returns) == 1:
        return sorted_returns[0]
    k = (len(sorted_returns) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_returns) - 1)
    if f == c:
        return sorted_returns[f]
    return sorted_returns[f] + (sorted_returns[c] - sorted_returns[f]) * (k - f)
