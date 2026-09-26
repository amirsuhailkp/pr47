from datetime import datetime, timezone

import pytest

from app.domain.market import CandidateEvidence, Instrument, Quote


def _instrument() -> Instrument:
    return Instrument(symbol="XYZ", exchange="NSE")


def test_quote_requires_timezone_aware_timestamp():
    with pytest.raises(ValueError):
        Quote(
            instrument=_instrument(),
            ltp=100.0,
            bid=99.5,
            ask=100.5,
            timestamp=datetime(2026, 9, 21, 10, 0),  # naive
            source="test",
            ingestion_timestamp=datetime.now(timezone.utc),
        )


def test_quote_accepts_aware_timestamp():
    q = Quote(
        instrument=_instrument(),
        ltp=100.0,
        bid=99.5,
        ask=100.5,
        timestamp=datetime.now(timezone.utc),
        source="test",
        ingestion_timestamp=datetime.now(timezone.utc),
    )
    assert q.ltp == 100.0


def test_candidate_evidence_requires_at_least_one_reason():
    with pytest.raises(ValueError):
        CandidateEvidence(
            instrument=_instrument(),
            generated_at=datetime.now(timezone.utc),
            reasons=[],
        )


def test_candidate_evidence_with_reason_is_valid():
    ev = CandidateEvidence(
        instrument=_instrument(),
        generated_at=datetime.now(timezone.utc),
        reasons=["high relative volume"],
        risks=["small historical sample"],
    )
    assert ev.reasons == ["high relative volume"]
