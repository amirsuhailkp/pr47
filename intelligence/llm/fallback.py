"""Deterministic fallback — used when every LLM provider fails.

docs/LLM_ARCHITECTURE.md: "If every LLM provider is unavailable, DataBroker still ...
generates alerts" — e.g. 'XYZ +4.8%, relative volume 3.2×, broke 20-day high.' This
builds an LLMAnalysis-shaped object from the same structured evidence, entirely
without a model call, so callers downstream never need to special-case "no LLM".
"""
from __future__ import annotations

from typing import Any

from app.domain.llm import LLMAnalysis


def build_fallback_analysis(evidence: dict[str, Any]) -> LLMAnalysis:
    observations = []

    price = evidence.get("price")
    change = evidence.get("price_change_pct")
    if price is not None and change is not None:
        direction = "up" if change >= 0 else "down"
        observations.append(f"Price is {direction} {abs(change):.2f}% at {price}")

    rel_vol = evidence.get("relative_volume")
    if rel_vol is not None:
        observations.append(f"Relative volume is {rel_vol:.2f}x the recent average")

    rsi = evidence.get("rsi_14")
    if rsi is not None:
        observations.append(f"RSI(14) is {rsi:.1f}")

    patterns = [p.get("family", "UNKNOWN") for p in evidence.get("detected_patterns", [])]

    risk_flags = list(evidence.get("risk_flags", []))

    summary_parts = [evidence.get("instrument_symbol", "Instrument")]
    if change is not None:
        summary_parts.append(f"{change:+.2f}%")
    if rel_vol is not None:
        summary_parts.append(f"relative volume {rel_vol:.1f}x")
    if patterns:
        summary_parts.append("pattern: " + ", ".join(patterns))
    summary = ", ".join(summary_parts) + "."

    return LLMAnalysis(
        summary=summary,
        observations=tuple(observations),
        patterns=tuple(patterns),
        historical_context=evidence.get("historical_cases") or {},
        possible_scenarios=(),
        risk_factors=tuple(risk_flags),
        invalidation_conditions=(),
        uncertainty=("Generated without LLM interpretation — deterministic summary only.",),
        missing_information=("LLM-based scenario analysis unavailable.",),
    )
