"""Credential pool for a single LLM provider.

docs/LLM_ARCHITECTURE.md §Multiple API keys: multiple keys exist to monitor usage,
respect Retry-After, back off exponentially, temporarily disable an exhausted
credential, and fail over to another *authorized* provider/model — never to route
around a provider's own rate limits.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class CredentialState:
    key: str
    disabled_until: datetime | None = None
    consecutive_failures: int = 0

    def is_available(self, now: datetime) -> bool:
        return self.disabled_until is None or now >= self.disabled_until


@dataclass
class CredentialPool:
    provider_name: str
    keys: list[str]
    base_backoff_seconds: float = 5.0
    max_backoff_seconds: float = 900.0
    _states: dict[str, CredentialState] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self._states = {k: CredentialState(key=k) for k in self.keys}

    def next_available(self, now: datetime) -> str | None:
        """Returns the first credential not currently in its cooldown window."""
        for key in self.keys:
            if self._states[key].is_available(now):
                return key
        return None

    def record_rate_limited(
        self, key: str, now: datetime, retry_after_seconds: float | None = None
    ) -> None:
        """Disables this credential temporarily. Honors an explicit Retry-After if the
        provider gave one; otherwise backs off exponentially per-credential."""
        state = self._states[key]
        state.consecutive_failures += 1
        if retry_after_seconds is not None:
            delay = retry_after_seconds
        else:
            delay = min(
                self.base_backoff_seconds * (2 ** (state.consecutive_failures - 1)),
                self.max_backoff_seconds,
            )
        state.disabled_until = now + timedelta(seconds=delay)

    def record_success(self, key: str) -> None:
        state = self._states[key]
        state.consecutive_failures = 0
        state.disabled_until = None

    def has_any_available(self, now: datetime) -> bool:
        return self.next_available(now) is not None
