"""Validates a raw LLM response dict against the required LLMAnalysis shape.

docs/LLM_ARCHITECTURE.md §Structured output & validation: on failure the caller must
retry, then try another provider/model, then fall back to deterministic analysis.
This module only does the validation step — the retry/failover chain lives in router.py.
"""
from __future__ import annotations

from app.domain.llm import LLM_ANALYSIS_SCHEMA, FORBIDDEN_CERTAINTY_PHRASES, LLMAnalysis


class LLMValidationError(Exception):
    pass


def _check_required_fields(data: dict) -> None:
    missing = [f for f in LLM_ANALYSIS_SCHEMA["required"] if f not in data]
    if missing:
        raise LLMValidationError(f"missing required field(s): {missing}")


def _check_types(data: dict) -> None:
    if not isinstance(data.get("summary"), str):
        raise LLMValidationError("'summary' must be a string")
    list_fields = [
        "observations", "patterns", "possible_scenarios", "risk_factors",
        "invalidation_conditions", "uncertainty", "missing_information",
    ]
    for f in list_fields:
        value = data.get(f)
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise LLMValidationError(f"'{f}' must be a list of strings")
    if not isinstance(data.get("historical_context"), dict):
        raise LLMValidationError("'historical_context' must be an object")


def _check_no_false_certainty(data: dict) -> None:
    """Reject responses containing hard directional/guarantee language — the LLM must
    interpret evidence, never assert a guaranteed outcome (docs §46)."""
    haystack = " ".join(
        [data.get("summary", "")] + data.get("observations", []) + data.get("possible_scenarios", [])
    ).lower()
    for phrase in FORBIDDEN_CERTAINTY_PHRASES:
        if phrase in haystack:
            raise LLMValidationError(f"response contains disallowed certainty language: '{phrase}'")


def validate_llm_response(data: dict) -> LLMAnalysis:
    _check_required_fields(data)
    _check_types(data)
    _check_no_false_certainty(data)

    return LLMAnalysis(
        summary=data["summary"],
        observations=tuple(data["observations"]),
        patterns=tuple(data["patterns"]),
        historical_context=data["historical_context"],
        possible_scenarios=tuple(data["possible_scenarios"]),
        risk_factors=tuple(data["risk_factors"]),
        invalidation_conditions=tuple(data["invalidation_conditions"]),
        uncertainty=tuple(data["uncertainty"]),
        missing_information=tuple(data["missing_information"]),
    )
