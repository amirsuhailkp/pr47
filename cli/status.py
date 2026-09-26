"""`python -m app.cli.status` — prints current system health (Phase 1 stub)."""
from __future__ import annotations

from app.services.health import collect_health


def main() -> None:
    health = collect_health()
    print(f"DataBroker status — overall: {health.overall_status()}")
    for c in health.components:
        print(f"  {c.name:<12} {c.status:<13} {c.detail}")


if __name__ == "__main__":
    main()
