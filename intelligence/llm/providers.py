"""Groq and Cerebras provider adapters implementing app.domain.providers.LLMProvider.

Network access is abstracted behind an injected `transport` callable so these are
unit-testable without any real HTTP call or API key. In production, `transport` is a
thin wrapper around an httpx POST to the provider's chat-completions endpoint.
"""
from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.domain.providers import LLMProvider
from intelligence.llm.credentials import CredentialPool

Transport = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]
"""transport(api_key, request_body) -> raw provider response dict."""


class RateLimitError(Exception):
    def __init__(self, retry_after_seconds: float | None = None) -> None:
        super().__init__("rate limited")
        self.retry_after_seconds = retry_after_seconds


class ProviderError(Exception):
    pass


def _extract_json(text: str) -> dict[str, Any]:
    """Strips ```json fences if present, then parses. Raises ProviderError on
    malformed output rather than guessing at partial content."""
    cleaned = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"model did not return valid JSON: {exc}") from exc


@dataclass
class _BaseCompletionProvider(LLMProvider):
    name: str
    default_model: str
    credential_pool: CredentialPool
    transport: Transport
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

    def _build_request(
        self, task_type: str, evidence: dict[str, Any], schema: dict[str, Any], model: str
    ) -> dict[str, Any]:
        instruction = (
            "You are a market-analysis assistant. Given the structured evidence "
            "below, respond with ONLY a JSON object matching this schema — no "
            "preamble, no markdown fences. Never invent prices, volumes, news, "
            "indicators or historical results not present in the evidence. Never "
            "assert a guaranteed outcome.\n\n"
            f"Schema: {json.dumps(schema)}\n\nEvidence: {json.dumps(evidence)}"
        )
        return {
            "model": model,
            "messages": [{"role": "user", "content": instruction}],
            "task_type": task_type,
        }

    async def complete_structured(
        self, task_type: str, evidence: dict[str, Any], schema: dict[str, Any]
    ) -> dict[str, Any]:
        now = self.clock()
        key = self.credential_pool.next_available(now)
        if key is None:
            raise ProviderError(f"{self.name}: no available credentials")

        request = self._build_request(task_type, evidence, schema, self.default_model)
        try:
            response = await self.transport(key, request)
        except RateLimitError as exc:
            self.credential_pool.record_rate_limited(key, now, exc.retry_after_seconds)
            raise ProviderError(f"{self.name}: rate limited") from exc

        self.credential_pool.record_success(key)

        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"{self.name}: unexpected response shape") from exc

        return _extract_json(content)

    async def health(self) -> dict[str, Any]:
        now = self.clock()
        return {
            "provider": self.name,
            "status": "OK" if self.credential_pool.has_any_available(now) else "DEGRADED",
        }


class GroqProvider(_BaseCompletionProvider):
    def __init__(
        self, credential_pool: CredentialPool, transport: Transport, default_model: str = "gpt-oss-120b"
    ) -> None:
        super().__init__(
            name="groq", default_model=default_model, credential_pool=credential_pool, transport=transport
        )


class CerebrasProvider(_BaseCompletionProvider):
    def __init__(
        self, credential_pool: CredentialPool, transport: Transport, default_model: str = "qwen-3-27b"
    ) -> None:
        super().__init__(
            name="cerebras", default_model=default_model, credential_pool=credential_pool, transport=transport
        )
