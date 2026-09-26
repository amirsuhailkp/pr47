"""Telegram notifier. Network access is abstracted behind an injected `transport`
callable (same pattern as intelligence/llm/providers.py) so this is unit-testable
without a real bot token or network call. Production wiring points `transport` at an
httpx POST to https://api.telegram.org/bot<token>/sendMessage.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.domain.providers import NotificationProvider

Transport = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]
"""transport(chat_id, request_body) -> raw Telegram API response dict."""


class TelegramSendError(Exception):
    pass


class TelegramNotifier(NotificationProvider):
    def __init__(self, bot_token: str, chat_id: str, transport: Transport) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._transport = transport

    async def send(self, payload: dict[str, Any]) -> None:
        text = payload.get("text")
        if not text:
            raise TelegramSendError("payload missing 'text'")

        try:
            response = await self._transport(self._chat_id, {"chat_id": self._chat_id, "text": text})
        except Exception as exc:  # noqa: BLE001 - network/provider errors, not our fault to interpret
            raise TelegramSendError(str(exc)) from exc

        if not response.get("ok", False):
            raise TelegramSendError(f"Telegram API returned not-ok: {response}")

    async def health(self) -> dict[str, Any]:
        return {"provider": "telegram", "status": "OK" if self._bot_token else "UNCONFIGURED"}
