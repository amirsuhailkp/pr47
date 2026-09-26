"""Name -> StrategyProfile lookup, used by the CLI/script and the /strategy Telegram
command so both refer to strategies by the same string."""
from __future__ import annotations

from market.strategies.profile import StrategyProfile
from market.strategies.scalping import SCALPING_PROFILE
from market.strategies.swing import SWING_PROFILE

STRATEGIES: dict[str, StrategyProfile] = {
    "scalping": SCALPING_PROFILE,
    "swing": SWING_PROFILE,
}


class UnknownStrategyError(Exception):
    pass


def get_strategy(name: str) -> StrategyProfile:
    try:
        return STRATEGIES[name.lower()]
    except KeyError as exc:
        raise UnknownStrategyError(
            f"unknown strategy '{name}' — known strategies: {sorted(STRATEGIES)}"
        ) from exc
