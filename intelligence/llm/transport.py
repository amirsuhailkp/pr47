"""Real network transports for the LLM providers (intelligence/llm/providers.py).

Both Groq and Cerebras expose an OpenAI-compatible chat-completions endpoint, so one
shape of request/response works for both — only the base URL differs. Kept separate
from providers.py so that module stays fully unit-testable with a fake transport and
no real HTTP/API key, per its own docstring.
"""
from __future__ import annotations

from typing import Any

from intelligence.llm.providers import ProviderError, RateLimitError

GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
CEREBRAS_CHAT_COMPLETIONS_URL = "https://api.cerebras.ai/v1/chat/completions"


async def _post_chat_completion(url: str, api_key: str, request: dict[str, Any]) -> dict[str, Any]:
    import httpx

    body = {
        "model": request["model"],
        "messages": request["messages"],
        "temperature": 0.2,
        # Alert enrichment must stay a short summary, not a report — capping tokens
        # here is a real cost control, not just a style preference.
        "max_tokens": 500,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
            )
    except httpx.RequestError as exc:
        raise ProviderError(f"network error calling {url}: {exc}") from exc

    if response.status_code == 429:
        retry_after_header = response.headers.get("retry-after")
        retry_after = float(retry_after_header) if retry_after_header else None
        raise RateLimitError(retry_after_seconds=retry_after)

    if response.status_code >= 400:
        raise ProviderError(f"{url} returned HTTP {response.status_code}: {response.text[:300]}")

    return response.json()


async def groq_transport(api_key: str, request: dict[str, Any]) -> dict[str, Any]:
    return await _post_chat_completion(GROQ_CHAT_COMPLETIONS_URL, api_key, request)


async def cerebras_transport(api_key: str, request: dict[str, Any]) -> dict[str, Any]:
    return await _post_chat_completion(CEREBRAS_CHAT_COMPLETIONS_URL, api_key, request)
