"""Candidate ranking (ML task 5 of 6, docs/ML_ARCHITECTURE.md).

Weights are explicit configuration, never learned-and-hidden magic numbers, and every
score returns its per-factor contribution breakdown — this is what keeps a ranking
model compliant with docs §45 "no blind scoring": a ranked candidate must always be
able to show its reasons.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RankingScore:
    total: float
    contributions: dict[str, float]

    def explain(self) -> list[str]:
        ordered = sorted(self.contributions.items(), key=lambda kv: abs(kv[1]), reverse=True)
        return [f"{name}: {value:+.3f}" for name, value in ordered]


@dataclass
class CandidateRankingModel:
    weights: dict[str, float]

    def score(self, factors: dict[str, float]) -> RankingScore:
        contributions = {
            name: weight * factors[name] for name, weight in self.weights.items() if name in factors
        }
        return RankingScore(total=sum(contributions.values()), contributions=contributions)


@dataclass
class EqualWeightBaselineRanking:
    """The baseline every learned/tuned ranking must beat: every available factor
    counted equally, with no domain judgment about which factors matter more."""

    factor_keys: tuple[str, ...] = field(default_factory=tuple)

    def score(self, factors: dict[str, float]) -> RankingScore:
        keys = self.factor_keys or tuple(factors.keys())
        contributions = {k: factors[k] for k in keys if k in factors}
        return RankingScore(total=sum(contributions.values()), contributions=contributions)
