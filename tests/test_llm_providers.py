import json
from datetime import datetime, timezone

import pytest

from intelligence.llm.credentials import CredentialPool
from intelligence.llm.providers import CerebrasProvider, GroqProvider, ProviderError, RateLimitError

NOW = datetime.now(timezone.utc)
SCHEMA = {"type": "object"}


def _ok_response(payload: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


@pytest.mark.asyncio
async def test_groq_provider_happy_path_parses_json_content():
    async def transport(key, request):
        assert key == "k1"
        return _ok_response({"summary": "ok"})

    pool = CredentialPool("groq", ["k1"])
    provider = GroqProvider(pool, transport)
    result = await provider.complete_structured("stock_analysis", {}, SCHEMA)
    assert result == {"summary": "ok"}


@pytest.mark.asyncio
async def test_provider_strips_markdown_fences():
    async def transport(key, request):
        return {"choices": [{"message": {"content": '```json\n{"summary": "ok"}\n```'}}]}

    pool = CredentialPool("cerebras", ["k1"])
    provider = CerebrasProvider(pool, transport)
    result = await provider.complete_structured("stock_analysis", {}, SCHEMA)
    assert result == {"summary": "ok"}


@pytest.mark.asyncio
async def test_provider_raises_on_malformed_json():
    async def transport(key, request):
        return {"choices": [{"message": {"content": "not json at all"}}]}

    pool = CredentialPool("groq", ["k1"])
    provider = GroqProvider(pool, transport)
    with pytest.raises(ProviderError):
        await provider.complete_structured("stock_analysis", {}, SCHEMA)


@pytest.mark.asyncio
async def test_rate_limit_disables_credential_and_raises_provider_error():
    async def transport(key, request):
        raise RateLimitError(retry_after_seconds=60)

    pool = CredentialPool("groq", ["k1"])
    provider = GroqProvider(pool, transport)
    with pytest.raises(ProviderError):
        await provider.complete_structured("stock_analysis", {}, SCHEMA)
    assert pool.next_available(NOW) is None


@pytest.mark.asyncio
async def test_no_available_credentials_raises_immediately():
    pool = CredentialPool("groq", ["k1"])
    pool.record_rate_limited("k1", NOW, retry_after_seconds=1000)

    async def transport(key, request):
        raise AssertionError("transport should not be called with no available key")

    provider = GroqProvider(pool, transport)
    provider.clock = lambda: NOW
    with pytest.raises(ProviderError):
        await provider.complete_structured("stock_analysis", {}, SCHEMA)


@pytest.mark.asyncio
async def test_health_reports_degraded_when_all_keys_cooling_down():
    pool = CredentialPool("groq", ["k1"])
    pool.record_rate_limited("k1", NOW, retry_after_seconds=1000)

    async def transport(key, request):
        return _ok_response({})

    provider = GroqProvider(pool, transport)
    provider.clock = lambda: NOW
    health = await provider.health()
    assert health["status"] == "DEGRADED"
