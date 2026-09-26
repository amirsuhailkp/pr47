"""Task-based LLM routing with failover and deterministic fallback.

docs/LLM_ARCHITECTURE.md §Routing: simple/medium/complex task tiers map to
fast/medium/strongest models; routing also weighs provider availability. On
structured-output validation failure: retry once, then try another provider, then
fall back to deterministic analysis — malformed output must never break monitoring.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.domain.llm import LLM_ANALYSIS_SCHEMA, LLMAnalysis
from app.domain.providers import LLMProvider
from intelligence.llm.fallback import build_fallback_analysis
from intelligence.llm.providers import ProviderError
from intelligence.llm.validation import LLMValidationError, validate_llm_response


class TaskTier(str, Enum):
    SIMPLE = "SIMPLE"
    MEDIUM = "MEDIUM"
    COMPLEX = "COMPLEX"


_TASK_TIER_MAP: dict[str, TaskTier] = {
    "alert_summary": TaskTier.SIMPLE,
    "short_explanation": TaskTier.SIMPLE,
    "classification": TaskTier.SIMPLE,
    "stock_analysis": TaskTier.MEDIUM,
    "news_interpretation": TaskTier.MEDIUM,
    "pattern_explanation": TaskTier.MEDIUM,
    "multi_source_research": TaskTier.COMPLEX,
    "strategy_analysis": TaskTier.COMPLEX,
    "deep_report": TaskTier.COMPLEX,
}


def classify_task(task_type: str) -> TaskTier:
    return _TASK_TIER_MAP.get(task_type, TaskTier.MEDIUM)


@dataclass
class RoutingEvent:
    task_type: str
    tier: TaskTier
    provider_attempted: str
    outcome: str  # "SUCCESS" | "VALIDATION_FAILED" | "PROVIDER_ERROR" | "FALLBACK"
    detail: str = ""


@dataclass
class LLMRouter:
    """`providers` is ordered by preference within a tier; every provider is tried,
    in order, before falling back to deterministic analysis."""

    providers: list[LLMProvider]
    max_validation_retries: int = 1
    failover_log: list[RoutingEvent] = field(default_factory=list)

    async def analyze(
        self, task_type: str, evidence: dict[str, Any]
    ) -> tuple[LLMAnalysis, bool]:
        """Returns (analysis, used_llm). used_llm is False when every provider failed
        and the deterministic fallback was used — callers can surface that honestly."""
        tier = classify_task(task_type)

        for provider in self.providers:
            attempts = 0
            while attempts <= self.max_validation_retries:
                attempts += 1
                try:
                    raw = await provider.complete_structured(
                        task_type, evidence, LLM_ANALYSIS_SCHEMA
                    )
                except ProviderError as exc:
                    self.failover_log.append(
                        RoutingEvent(task_type, tier, provider.name, "PROVIDER_ERROR", str(exc))
                    )
                    break  # move to next provider, don't keep retrying a dead one

                try:
                    analysis = validate_llm_response(raw)
                except LLMValidationError as exc:
                    self.failover_log.append(
                        RoutingEvent(task_type, tier, provider.name, "VALIDATION_FAILED", str(exc))
                    )
                    continue  # retry same provider, up to max_validation_retries

                self.failover_log.append(
                    RoutingEvent(task_type, tier, provider.name, "SUCCESS")
                )
                return analysis, True

        self.failover_log.append(
            RoutingEvent(task_type, tier, "none", "FALLBACK", "all providers exhausted")
        )
        return build_fallback_analysis(evidence), False
