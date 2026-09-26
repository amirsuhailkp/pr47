"""Ranks CandidateEvidence objects from opportunity/discovery/engine.py.

Uses the existing explainable ranking model (ml/models/ranking/) rather than a new
scoring scheme — every ranked candidate keeps its full reasons/risks plus a
transparent factor breakdown, never a bare number (docs §45).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.market import CandidateEvidence
from ml.models.ranking.model import CandidateRankingModel, RankingScore

DEFAULT_WEIGHTS = {"reason_count": 1.0, "risk_count": -0.5}


@dataclass(frozen=True)
class RankedCandidate:
    evidence: CandidateEvidence
    score: RankingScore


def _factors_for(evidence: CandidateEvidence) -> dict[str, float]:
    return {
        "reason_count": float(len(evidence.reasons)),
        "risk_count": float(len(evidence.risks)),
    }


def rank_candidates(
    candidates: list[CandidateEvidence], weights: dict[str, float] = DEFAULT_WEIGHTS
) -> list[RankedCandidate]:
    model = CandidateRankingModel(weights=weights)
    ranked = [
        RankedCandidate(evidence=c, score=model.score(_factors_for(c))) for c in candidates
    ]
    ranked.sort(key=lambda rc: rc.score.total, reverse=True)
    return ranked
