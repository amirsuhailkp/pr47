"""Strategy definition — docs/PROJECT_PLAN.md §24 'Strategy research'.

A strategy is a hypothesis, never a claim: "let's test how setup X behaved
historically," not "strategy X works." Every field below is required precisely so a
strategy can't be added without stating its own limitations and invalidation
conditions up front.
"""
from __future__ import annotations

from dataclasses import dataclass


def _require_nonempty(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty description")


@dataclass(frozen=True)
class StrategyDefinition:
    name: str
    hypothesis: str
    setup_conditions: str
    confirmation: str
    invalidation: str
    timeframe: str
    required_data: str
    costs_and_slippage_notes: str
    liquidity_assumptions: str
    limitations: str

    def __post_init__(self) -> None:
        for field_name in (
            "name", "hypothesis", "setup_conditions", "confirmation", "invalidation",
            "timeframe", "required_data", "costs_and_slippage_notes",
            "liquidity_assumptions", "limitations",
        ):
            _require_nonempty(getattr(self, field_name), field_name)

    def as_text(self) -> str:
        return (
            f"Strategy: {self.name}\n"
            f"Timeframe: {self.timeframe}\n\n"
            f"Hypothesis: {self.hypothesis}\n\n"
            f"Setup: {self.setup_conditions}\n"
            f"Confirmation: {self.confirmation}\n"
            f"Invalidation: {self.invalidation}\n\n"
            f"Required data: {self.required_data}\n"
            f"Costs/slippage: {self.costs_and_slippage_notes}\n"
            f"Liquidity assumptions: {self.liquidity_assumptions}\n\n"
            f"Limitations: {self.limitations}"
        )
