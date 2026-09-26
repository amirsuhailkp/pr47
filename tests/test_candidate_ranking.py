from datetime import datetime, timezone

from app.domain.market import CandidateEvidence, Instrument
from opportunity.ranking.rank import rank_candidates

NOW = datetime.now(timezone.utc)


def _candidate(symbol: str, reasons: list[str], risks: list[str]) -> CandidateEvidence:
    return CandidateEvidence(
        instrument=Instrument(symbol=symbol, exchange="NSE"),
        generated_at=NOW,
        reasons=reasons,
        risks=risks,
    )


def test_more_reasons_ranks_higher():
    strong = _candidate("A", reasons=["r1", "r2", "r3"], risks=[])
    weak = _candidate("B", reasons=["r1"], risks=[])
    ranked = rank_candidates([weak, strong])
    assert [rc.evidence.instrument.symbol for rc in ranked] == ["A", "B"]


def test_more_risks_ranks_lower_for_equal_reasons():
    risky = _candidate("A", reasons=["r1", "r2"], risks=["risk1", "risk2"])
    safe = _candidate("B", reasons=["r1", "r2"], risks=[])
    ranked = rank_candidates([risky, safe])
    assert [rc.evidence.instrument.symbol for rc in ranked] == ["B", "A"]


def test_score_is_explainable():
    c = _candidate("A", reasons=["r1", "r2"], risks=["risk1"])
    ranked = rank_candidates([c])
    assert ranked[0].score.contributions == {"reason_count": 2.0, "risk_count": -0.5}
    assert ranked[0].score.total == 1.5
