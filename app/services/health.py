"""Aggregates health of market feed, database, Telegram and LLM providers for /status.

Phase 1 provides the shape; real provider checks are wired in as each provider lands
in later phases.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ComponentHealth:
    name: str
    status: str  # "OK" | "DEGRADED" | "DOWN" | "UNCONFIGURED"
    detail: str = ""


@dataclass
class SystemHealth:
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    components: list[ComponentHealth] = field(default_factory=list)

    def overall_status(self) -> str:
        statuses = {c.status for c in self.components}
        if "DOWN" in statuses:
            return "DOWN"
        if "DEGRADED" in statuses:
            return "DEGRADED"
        return "OK"


def collect_health() -> SystemHealth:
    """Phase 1 stub: reports component presence/configuration only.

    Phases 2-4 replace each UNCONFIGURED placeholder with a real check
    (websocket status, DB ping, Telegram getMe, LLM provider health).
    """
    from app.config.settings import get_settings

    settings = get_settings()
    components = [
        ComponentHealth("market_feed", "UNCONFIGURED", "no market data provider wired yet"),
        ComponentHealth(
            "database", "OK" if settings.database.database_url else "UNCONFIGURED"
        ),
        ComponentHealth(
            "telegram",
            "UNCONFIGURED" if not settings.telegram.bot_token else "OK",
        ),
        ComponentHealth(
            "groq",
            "UNCONFIGURED" if not settings.llm.groq_keys() else "OK",
        ),
        ComponentHealth(
            "cerebras",
            "UNCONFIGURED" if not settings.llm.cerebras_keys() else "OK",
        ),
    ]
    return SystemHealth(components=components)
