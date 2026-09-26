# DataBroker — Telegram

Telegram is the sole notification channel for v1. `alerts/telegram/TelegramNotifier` receives
already-structured objects (`AlertRecord`, summaries) and only formats/sends — it holds no
market-analysis logic itself.

## Message types (phased in)

- Immediate alerts (event/pattern-triggered)
- Watchlist alerts
- Daily summary, market-open summary, market-close summary
- Important-news alerts
- Candidate alerts
- Risk alerts

## Commands (architected for, not all built in v1)

```
/status              system + provider health
/market               index & sector snapshot
/watchlist            current watchlist
/analyze SYMBOL        deterministic analysis for a symbol
/why SYMBOL            evidence behind the latest alert/candidate for a symbol
/history SYMBOL        historical similarity summary for a symbol
/news SYMBOL           recent linked news
/candidates            current candidate list with evidence
/alerts                recent alerts
/strategy momentum     strategy research summary
/config                current effective configuration (non-secret)
```

Commands are dispatched through a small command router so new commands can be added without
touching notification/formatting logic.

## Delivery reliability

Failed sends are queued and retried, not dropped. Formatting failures fail closed (log + skip)
rather than sending a malformed message.

## Setup

`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` come from `.env` (see CONFIGURATION.md). Never logged,
never committed.
