"""LLM request/response domain models — docs/DATA_MODEL.md §LLM objects.

LLMAnalysis is the only shape a validated LLM response may take. It never contains a
raw prediction or a bare "buy/sell" signal — see docs/LLM_ARCHITECTURE.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StructuredEvidence:
    """What gets sent to the LLM. Every field is something deterministic code already
    computed — the LLM interprets this, it never receives an open "will it go up?"
    question (docs/LLM_ARCHITECTURE.md §29)."""

    instrument_symbol: str
    price: float
    price_change_pct: float | None
    relative_volume: float | None
    rsi_14: float | None
    vwap: float | None
    market_context: dict[str, Any]
    sector_context: dict[str, Any] | None
    detected_patterns: list[dict[str, Any]]
    historical_cases: dict[str, Any] | None
    news: list[dict[str, Any]]
    risk_flags: list[str]

    def to_payload(self) -> dict[str, Any]:
        return {
            "instrument_symbol": self.instrument_symbol,
            "price": self.price,
            "price_change_pct": self.price_change_pct,
            "relative_volume": self.relative_volume,
            "rsi_14": self.rsi_14,
            "vwap": self.vwap,
            "market_context": self.market_context,
            "sector_context": self.sector_context,
            "detected_patterns": self.detected_patterns,
            "historical_cases": self.historical_cases,
            "news": self.news,
            "risk_flags": self.risk_flags,
        }


LLM_ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "observations": {"type": "array", "items": {"type": "string"}},
        "patterns": {"type": "array", "items": {"type": "string"}},
        "historical_context": {"type": "object"},
        "possible_scenarios": {"type": "array", "items": {"type": "string"}},
        "risk_factors": {"type": "array", "items": {"type": "string"}},
        "invalidation_conditions": {"type": "array", "items": {"type": "string"}},
        "uncertainty": {"type": "array", "items": {"type": "string"}},
        "missing_information": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "summary", "observations", "patterns", "historical_context",
        "possible_scenarios", "risk_factors", "invalidation_conditions",
        "uncertainty", "missing_information",
    ],
}

FORBIDDEN_CERTAINTY_PHRASES = ("will go up", "will go down", "guaranteed", "buy this", "sell this")


@dataclass(frozen=True)
class LLMAnalysis:
    summary: str
    observations: tuple[str, ...] = field(default_factory=tuple)
    patterns: tuple[str, ...] = field(default_factory=tuple)
    historical_context: dict[str, Any] = field(default_factory=dict)
    possible_scenarios: tuple[str, ...] = field(default_factory=tuple)
    risk_factors: tuple[str, ...] = field(default_factory=tuple)
    invalidation_conditions: tuple[str, ...] = field(default_factory=tuple)
    uncertainty: tuple[str, ...] = field(default_factory=tuple)
    missing_information: tuple[str, ...] = field(default_factory=tuple)
