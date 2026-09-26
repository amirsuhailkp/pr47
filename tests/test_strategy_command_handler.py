import pytest

from alerts.telegram.commands import CommandRouter
from alerts.telegram.handlers import strategy_command_handler


@pytest.mark.asyncio
async def test_strategy_command_with_no_args_lists_strategies():
    router = CommandRouter()
    router.register("/strategy", strategy_command_handler)
    result = await router.dispatch("/strategy")
    assert "scalping" in result
    assert "swing" in result


@pytest.mark.asyncio
async def test_strategy_command_with_name_shows_full_definition():
    router = CommandRouter()
    router.register("/strategy", strategy_command_handler)
    result = await router.dispatch("/strategy swing")
    assert "Swing" in result
    assert "Hypothesis" in result
    assert "Limitations" in result


@pytest.mark.asyncio
async def test_strategy_command_unknown_name_returns_friendly_message():
    router = CommandRouter()
    router.register("/strategy", strategy_command_handler)
    result = await router.dispatch("/strategy nonexistent")
    assert "unknown strategy" in result.lower()
