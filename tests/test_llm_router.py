import pytest

from app.domain.providers import LLMProvider
from intelligence.llm.providers import ProviderError
from intelligence.llm.router import LLMRouter, TaskTier, classify_task

VALID_RESPONSE = {
    "summary": "ok", "observations": [], "patterns": [], "historical_context": {},
    "possible_scenarios": [], "risk_factors": [], "invalidation_conditions": [],
    "uncertainty": [], "missing_information": [],
}


class ScriptedProvider(LLMProvider):
    """Returns a scripted sequence of responses/exceptions, one per call."""

    def __init__(self, name: str, script: list):
        self.name = name
        self._script = list(script)
        self.calls = 0

    async def complete_structured(self, task_type, evidence, schema):
        self.calls += 1
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def health(self):
        return {"status": "OK"}


@pytest.mark.asyncio
async def test_router_succeeds_on_first_provider():
    provider = ScriptedProvider("groq", [VALID_RESPONSE])
    router = LLMRouter(providers=[provider])
    analysis, used_llm = await router.analyze("stock_analysis", {})
    assert used_llm is True
    assert analysis.summary == "ok"
    assert router.failover_log[-1].outcome == "SUCCESS"


@pytest.mark.asyncio
async def test_router_retries_same_provider_on_validation_failure_then_succeeds():
    bad = {"summary": "ok"}  # missing required fields
    provider = ScriptedProvider("groq", [bad, VALID_RESPONSE])
    router = LLMRouter(providers=[provider], max_validation_retries=1)
    analysis, used_llm = await router.analyze("stock_analysis", {})
    assert used_llm is True
    assert provider.calls == 2
    outcomes = [e.outcome for e in router.failover_log]
    assert outcomes == ["VALIDATION_FAILED", "SUCCESS"]


@pytest.mark.asyncio
async def test_router_fails_over_to_next_provider_on_provider_error():
    groq = ScriptedProvider("groq", [ProviderError("rate limited")])
    cerebras = ScriptedProvider("cerebras", [VALID_RESPONSE])
    router = LLMRouter(providers=[groq, cerebras])
    analysis, used_llm = await router.analyze("stock_analysis", {})
    assert used_llm is True
    assert analysis.summary == "ok"
    outcomes = [(e.provider_attempted, e.outcome) for e in router.failover_log]
    assert outcomes == [("groq", "PROVIDER_ERROR"), ("cerebras", "SUCCESS")]


@pytest.mark.asyncio
async def test_router_falls_back_to_deterministic_when_all_providers_fail():
    groq = ScriptedProvider("groq", [ProviderError("down")])
    cerebras = ScriptedProvider("cerebras", [ProviderError("down")])
    router = LLMRouter(providers=[groq, cerebras])
    evidence = {"instrument_symbol": "XYZ", "price_change_pct": 3.0}
    analysis, used_llm = await router.analyze("stock_analysis", evidence)
    assert used_llm is False
    assert "XYZ" in analysis.summary
    assert router.failover_log[-1].outcome == "FALLBACK"


@pytest.mark.asyncio
async def test_router_falls_back_after_exhausting_validation_retries():
    always_bad = {"summary": "ok"}  # never has required fields
    provider = ScriptedProvider("groq", [always_bad, always_bad])
    router = LLMRouter(providers=[provider], max_validation_retries=1)
    analysis, used_llm = await router.analyze("stock_analysis", {})
    assert used_llm is False
    assert provider.calls == 2


def test_classify_task_tiers():
    assert classify_task("alert_summary") == TaskTier.SIMPLE
    assert classify_task("stock_analysis") == TaskTier.MEDIUM
    assert classify_task("deep_report") == TaskTier.COMPLEX
    assert classify_task("unknown_task") == TaskTier.MEDIUM
