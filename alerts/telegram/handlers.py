"""Concrete handlers for CommandRouter (alerts/telegram/commands.py). Handlers only
produce text — they never format or send; the router and notifier own those steps.
"""
from __future__ import annotations

from market.strategies.registry import STRATEGIES, UnknownStrategyError, get_strategy


async def strategy_command_handler(args: list[str]) -> str:
    """`/strategy` lists available strategies; `/strategy <name>` shows its full
    definition (hypothesis, setup, confirmation, invalidation, limitations)."""
    if not args:
        names = ", ".join(sorted(STRATEGIES))
        return f"Available strategies: {names}\nUse /strategy <name> for details."

    try:
        profile = get_strategy(args[0])
    except UnknownStrategyError as exc:
        return str(exc)

    return profile.definition.as_text()
