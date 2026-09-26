"""Formats an AlertRecord into the Telegram message text (docs/ALERT_ARCHITECTURE.md
example shape). Contains no market-analysis logic — it only renders what it's given.
"""
from __future__ import annotations

from app.domain.patterns import AlertRecord, Severity

_SEVERITY_EMOJI = {
    Severity.INFO: "ℹ️",
    Severity.WATCH: "👀",
    Severity.IMPORTANT: "⚠️",
    Severity.CRITICAL: "🚨",
}


def format_alert(alert: AlertRecord) -> str:
    emoji = _SEVERITY_EMOJI[alert.severity]
    lines = [
        f"{emoji} {alert.severity.value} ACTIVITY",
        f"{alert.instrument.symbol} — {alert.instrument.exchange}",
        "",
        alert.title,
    ]
    if alert.body_lines:
        lines.append("")
        lines.extend(alert.body_lines)
    if alert.risks:
        lines.append("")
        lines.append("Risks:")
        lines.extend(f"• {r}" for r in alert.risks)
    lines.append("")
    lines.append("This is market analysis, not a guaranteed outcome.")
    return "\n".join(lines)
