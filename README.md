# DataBroker

A personal market-intelligence and alerting system for the Indian stock market (NSE). DataBroker
watches the market, detects meaningful changes, checks them against history, and explains what it
found over Telegram — it does not trade, and it does not claim to know the future.

This is a new project, built from scratch. See `docs/PROJECT_PLAN.md` for how it relates (or
deliberately doesn't) to any earlier repository.

## What it does

1. Monitors NSE main-board equities in real time.
2. Detects important price/volume/technical/news/market changes.
3. Matches current situations against historical setups.
4. Surfaces candidates worth investigating, with explicit reasons and risks.
5. Sends Telegram alerts — deterministic by default, LLM-enriched when available.

## What it deliberately does not do

- Place trades automatically.
- Output bare "BUY THIS STOCK" signals.
- Depend on any LLM to function — the deterministic pipeline works with every LLM provider
  offline.

## Architecture

Read in this order:

1. `docs/ARCHITECTURE.md` — layered pipeline, package map, runtime services
2. `docs/PROJECT_PLAN.md` — build phases and rules
3. `docs/DATA_MODEL.md` — canonical objects
4. `docs/CONFIGURATION.md` — environment variables
5. `docs/LLM_ARCHITECTURE.md`, `docs/ALERT_ARCHITECTURE.md`, `docs/ML_ARCHITECTURE.md`
6. `docs/AZURE_DEPLOYMENT.md`, `docs/TELEGRAM.md`, `docs/TESTING.md`

## Project layout

```
app/            configuration, domain contracts, services, orchestration
data/           ingestion, normalization, provider adapters, storage, schemas
market/         universe, session calendar, indicators, analytics, sector/regime context
patterns/       momentum, breakout, pullback + extensible pattern engine
history/        historical datasets, similarity, outcomes, backtesting
opportunity/    candidate discovery, ranking, evidence
ml/             optional models — anomaly, similarity, ranking, regime
intelligence/   LLM providers, router, prompts, research
alerts/         rules, severity, dedup, Telegram
infrastructure/ Azure runtime + deployment config
cli/            local operator commands
tests/          unit + integration tests
scripts/        one-off / maintenance scripts
docs/           architecture documents
```

## Setup (Phase 1)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in real values — never commit .env
```

Configuration is validated at startup; see `docs/CONFIGURATION.md` for every key.

## Temporary testing setup (free/keyless providers)

Before a broker account (KYC, real WebSocket feed) is wired in, `scripts/run_local_test.py`
runs the real Phase 2–4 pipeline end to end against free sources — no code changes needed,
since these are just new adapters behind the existing `MarketDataProvider` /
`HistoricalDataProvider` / `NewsProvider` interfaces:

| Need | Source | Key required? |
|---|---|---|
| Live quote (demo) | [IndianAPI.in](https://indianapi.in) | Yes, free tier |
| Historical backfill (daily bars) | `yfinance` | No |
| News | BSE notices RSS + Google News RSS | No |
| Alert delivery | Telegram Bot API | Yes, free (via @BotFather) |

Setup:

```bash
pip install -r requirements.txt          # now includes yfinance
cp .env.example .env
```

Fill in `.env`:
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — message @BotFather for a token; get your
  chat ID by messaging your bot once and checking `https://api.telegram.org/bot<token>/getUpdates`
- `INDIANAPI_API_KEY` — optional; only powers the live-quote printout. Sign up free at
  https://indianapi.in and grab the key from your dashboard's API/Manage Keys section.
  Backfill and pipeline evaluation use `yfinance` regardless, so this can be left blank.
- `WATCHLIST_SYMBOLS` — comma-separated NSE symbols, e.g. `TCS,RELIANCE,INFY`

Run:

```bash
python -m scripts.run_local_test                                # swing (default), WATCHLIST_SYMBOLS from .env
python -m scripts.run_local_test --strategy scalping             # scalping, same watchlist
python -m scripts.run_local_test --strategy swing RELIANCE TCS   # explicit symbols
```

`--strategy` selects between two profiles (`market/strategies/`), each with its own
bar interval, pattern thresholds, and alert cooldown — not just a label:

| | Scalping | Swing |
|---|---|---|
| Bar interval | 5-minute | Daily |
| Momentum trigger | >=0.3% move, 1.2x rel. volume | >=2.0% move, 1.5x rel. volume |
| Alert cooldown | 5 minutes | 4 hours |
| Backfill window | 5 days | 180 days |

Each has a full written strategy definition (hypothesis, setup, confirmation,
invalidation, costs/liquidity notes, limitations — `docs`-style, per
`app/domain/strategy.py`) viewable via the `/strategy <name>` Telegram command once
wired to a live bot, or directly: `market.strategies.swing.SWING_DEFINITION.as_text()`.

This backfills bars via `yfinance` at whichever interval the chosen strategy uses, runs
the real pattern/event detection and alert engine against them, persists any alerts to
the local SQLite DB, attempts real Telegram delivery (queuing/retrying on failure
exactly as in production), and prints recent BSE/Google News items plus (if
`INDIANAPI_API_KEY` is set) a live quote.

Scalping's 5-minute backfill is still yfinance REST data, not live intraday ticks —
useful for testing the deterministic logic at that resolution, but not a substitute
for a real broker's intraday feed (see `docs/PROJECT_PLAN.md`).

## Finding candidates (scanning the exchange, not just named symbols)

`scripts/run_local_test.py` only checks symbols you name. To scan the actual NSE
universe and surface candidates worth investigating, use:

```bash
python -m scripts.discover_candidates                              # swing, first 40 symbols
python -m scripts.discover_candidates --strategy scalping --limit 20
python -m scripts.discover_candidates --limit 200 --top 15          # scan more, show more
```

This fetches the real, free NSE main-board equity list (~2,600 symbols, no API key —
`data/providers/nse_universe_provider.py`), applies the price/liquidity/data-quality
universe filter to each, runs the chosen strategy's pattern/event detection, and
prints the ranked candidates with their full reasons and risks — never a bare score.

`--limit` caps how many symbols are actually scanned (one yfinance call per symbol,
so scanning the full universe is slow and rate-limit-prone on a free setup); raise it
if you want a wider scan, or wire in a real broker's bulk-quote endpoint later to
remove this constraint entirely.

## Running locally

Phase 1 provides configuration loading, domain models, the market-session engine, provider
interfaces, and a minimal health check. Real-time ingestion, analytics, patterns, historical
engine, LLM routing and ML land in Phases 2–5 (see `docs/PROJECT_PLAN.md`).

```bash
python -m cli.status
```

## Testing

```bash
pytest
```

See `docs/TESTING.md` for coverage expectations.

## Status

Phase 1 (foundation) — in progress. See `docs/PROJECT_PLAN.md` for the full roadmap.
