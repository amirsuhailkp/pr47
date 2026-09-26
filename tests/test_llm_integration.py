from datetime import datetime, timedelta, timezone

import pytest

from app.domain.market import IndexSnapshot, Instrument, OHLCVBar
from app.domain.providers import LLMProvider
from intelligence.llm.evidence_builder import build_evidence
from intelligence.llm.router import LLMRouter
from market.analytics.context import build_context
from market.analytics.price_volume import build_snapshot
from patterns.breakout.detector import BreakoutDetector
from patterns.engine.base import PatternEngine
from patterns.momentum.detector import MomentumDetector

INSTRUMENT = Instrument(symbol="XYZ", exchange="NSE")


def _bars(closes, volumes):
    out = []
    for i, (c, v) in enumerate(zip(closes, volumes)):
        ts = datetime(2026, 9, 21, 9, 15, tzinfo=timezone.utc) + timedelta(minutes=i)
        out.append(
            OHLCVBar(
                instrument=INSTRUMENT, interval="1m", open=c, high=c * 1.01, low=c * 0.99,
                close=c, volume=v, timestamp=ts, source="test", ingestion_timestamp=ts,
            )
        )
    return out


class EchoProvider(LLMProvider):
    """A fake provider that reflects the evidence back as a valid structured analysis
    — proves the router/evidence path works without any network dependency."""

    name = "echo"

    async def complete_structured(self, task_type, evidence, schema):
        symbol = evidence["instrument_symbol"]
        patterns = [p["family"] for p in evidence["detected_patterns"]]
        return {
            "summary": f"{symbol} showing {', '.join(patterns) or 'no notable pattern'}.",
            "observations": [f"relative_volume={evidence.get('relative_volume')}"],
            "patterns": patterns,
            "historical_context": evidence.get("historical_cases") or {},
            "possible_scenarios": ["Continuation if volume persists."],
            "risk_factors": list(evidence.get("risk_flags", [])),
            "invalidation_conditions": ["close back below breakout level"],
            "uncertainty": ["evidence-based interpretation only"],
            "missing_information": [],
        }

    async def health(self):
        return {"status": "OK"}


@pytest.mark.asyncio
async def test_pattern_evidence_flows_through_router_to_validated_analysis():
    closes = [100 + i * 0.3 for i in range(59)] + [140.0]
    volumes = [1000] * 59 + [6000]
    bars = _bars(closes, volumes)
    as_of = bars[-1].timestamp

    snapshot = build_snapshot(bars)
    market_index = IndexSnapshot(
        code="NIFTY50", value=20000, change=100, change_pct=0.5, timestamp=as_of, source="test"
    )
    context = build_context(snapshot.price_change_pct or 0.0, market_index, None)

    engine = PatternEngine([MomentumDetector(), BreakoutDetector()])
    patterns = engine.run(INSTRUMENT, snapshot, context, as_of)
    assert patterns  # sanity: the synthetic spike should trip at least one detector

    evidence = build_evidence(INSTRUMENT, snapshot, context, patterns, risk_flags=["thin sample"])
    router = LLMRouter(providers=[EchoProvider()])
    analysis, used_llm = await router.analyze("stock_analysis", evidence.to_payload())

    assert used_llm is True
    assert "XYZ" in analysis.summary
    assert "thin sample" in analysis.risk_factors
    assert any(p in analysis.patterns for p in ["MOMENTUM", "BREAKOUT"])
