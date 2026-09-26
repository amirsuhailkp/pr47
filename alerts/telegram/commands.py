"""Command dispatch (docs/TELEGRAM.md). Only /status and /candidates are wired in
Phase 1/2 scope — the router itself is built so new commands register cleanly without
touching notification/formatting logic, per docs' "not all commands in v1" note.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

Handler = Callable[[list[str]], Awaitable[str]]


class UnknownCommandError(Exception):
    pass


class CommandRouter:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, command: str, handler: Handler) -> None:
        if not command.startswith("/"):
            raise ValueError("commands must start with '/'")
        self._handlers[command] = handler

    async def dispatch(self, message_text: str) -> str:
        parts = message_text.strip().split()
        if not parts:
            raise UnknownCommandError("empty message")
        command, *args = parts
        handler = self._handlers.get(command)
        if handler is None:
            raise UnknownCommandError(command)
        return await handler(args)

    def known_commands(self) -> list[str]:
        return sorted(self._handlers.keys())
