import pytest

from alerts.telegram.commands import CommandRouter, UnknownCommandError


@pytest.mark.asyncio
async def test_register_and_dispatch():
    router = CommandRouter()

    async def status_handler(args):
        return "all OK"

    router.register("/status", status_handler)
    result = await router.dispatch("/status")
    assert result == "all OK"


@pytest.mark.asyncio
async def test_dispatch_passes_args():
    router = CommandRouter()

    async def analyze_handler(args):
        return f"analyzing {args[0]}"

    router.register("/analyze", analyze_handler)
    result = await router.dispatch("/analyze XYZ")
    assert result == "analyzing XYZ"


@pytest.mark.asyncio
async def test_dispatch_unknown_command_raises():
    router = CommandRouter()
    with pytest.raises(UnknownCommandError):
        await router.dispatch("/nope")


@pytest.mark.asyncio
async def test_dispatch_empty_message_raises():
    router = CommandRouter()
    with pytest.raises(UnknownCommandError):
        await router.dispatch("   ")


def test_register_requires_leading_slash():
    router = CommandRouter()
    with pytest.raises(ValueError):
        router.register("status", lambda args: None)


def test_known_commands_sorted():
    router = CommandRouter()
    router.register("/status", lambda args: None)
    router.register("/analyze", lambda args: None)
    assert router.known_commands() == ["/analyze", "/status"]
