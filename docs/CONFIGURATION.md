# DataBroker — Configuration

All configuration is explicit and environment-driven. Nothing that varies by market, universe,
provider or threshold is hard-coded into logic.

## Loading

`app/config/` defines typed settings objects (e.g. via pydantic-settings) loaded from environment
variables / `.env`, validated at startup, and injected into services — never read ad hoc from
`os.environ` deep in business logic.

## Key groups

### Market & universe
```
MARKET=INDIA
EXCHANGE=NSE
MIN_PRICE=50
MAX_PRICE=300
MIN_AVG_TRADED_VALUE=...
EXCLUDE_SME=true
MIN_HISTORY_DAYS=...
```

### Database & storage
```
DATABASE_URL=...
ANALYTICAL_STORAGE_URI=...   # blob/parquet root
```

### Market data provider(s)
```
MARKET_DATA_PROVIDER=...
MARKET_DATA_API_KEY=...
MARKET_DATA_WS_URL=...
```

### News / company data providers
```
NEWS_PROVIDER=...
NEWS_API_KEY=...
COMPANY_DATA_PROVIDER=...
```

### LLM providers (multiple credentials allowed per provider)
```
GROQ_API_KEYS=key1,key2
CEREBRAS_API_KEYS=key1
LLM_DEFAULT_ROUTING_PROFILE=cost_aware
```
Multiple keys are for failover/quota headroom only — never for circumventing provider rate
limits. See LLM_ARCHITECTURE.md §Multiple API keys.

### Telegram
```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

### Alerts
```
ALERT_SEVERITY_THRESHOLDS=...   # structured, per event category
ALERT_COOLDOWN_SECONDS=...
```

### Azure / deployment
```
AZURE_SUBSCRIPTION_ID=...
AZURE_RESOURCE_GROUP=...
DEPLOY_ENV=local|staging|production
```

## Rules

- `.env` is never committed; `.env.example` documents every key with a safe placeholder.
- Secrets are never logged (see TESTING.md and ARCHITECTURE.md §Security expectations).
- Universe bounds, thresholds and provider choices must be changeable without a code change.
- Config objects are validated eagerly — an invalid or missing required value fails startup
  loudly rather than degrading silently at runtime.
