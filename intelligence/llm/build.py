"""Wires the LLM layer (router/providers/credentials) to real configuration.

This is the piece that was missing end to end: intelligence/llm/router.py,
providers.py and credentials.py were fully built and unit-tested in isolation, but
nothing in app/orchestration or scripts/ ever constructed a real LLMRouter from
GROQ_API_KEYS / CEREBRAS_API_KEYS — so those keys were never actually used, no matter
what was in .env.
"""
from __future__ import annotations

from app.config.settings import LLMSettings
from app.domain.providers import LLMProvider
from intelligence.llm.credentials import CredentialPool
from intelligence.llm.providers import CerebrasProvider, GroqProvider
from intelligence.llm.router import LLMRouter
from intelligence.llm.transport import cerebras_transport, groq_transport

PRIMARY_MODEL = "gpt-oss-120b"  # Groq — tried first, every call
SECONDARY_MODEL = "qwen-3-27b"  # Cerebras — only tried once every Groq key is
# exhausted/rate-limited (see LLMRouter.analyze: it only advances to the next
# provider in the list after the current one raises ProviderError). Pinned here
# explicitly, rather than relying on GroqProvider/CerebrasProvider's own defaults, so
# the intended primary/secondary model choice lives in exactly one place and can't
# drift if those classes' defaults ever change.


def build_llm_router_from_settings(llm_settings: LLMSettings) -> LLMRouter | None:
    """One model per provider, tried strictly in this order — never both at once,
    never round-robin between them: PRIMARY_MODEL (Groq) on every call while its key
    pool has any available credential; SECONDARY_MODEL (Cerebras) only once every Groq
    key is in cooldown. The next call still starts from Groq again, so it recovers
    automatically once a Groq key's cooldown expires — no separate "come back" logic
    needed, per CredentialPool's cooldown-based availability check.

    Returns None when no provider has a key configured, so callers can skip LLM
    enrichment entirely (no cost, no behavior change) rather than build a router with
    zero providers.
    """
    providers: list[LLMProvider] = []

    groq_keys = llm_settings.groq_keys()
    if groq_keys:
        providers.append(
            GroqProvider(CredentialPool("groq", groq_keys), groq_transport, default_model=PRIMARY_MODEL)
        )

    cerebras_keys = llm_settings.cerebras_keys()
    if cerebras_keys:
        providers.append(
            CerebrasProvider(
                CredentialPool("cerebras", cerebras_keys), cerebras_transport, default_model=SECONDARY_MODEL
            )
        )

    if not providers:
        return None
    return LLMRouter(providers=providers)
