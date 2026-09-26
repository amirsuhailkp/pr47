# DataBroker — LLM Architecture

## Role of the LLM

The LLM interprets and synthesizes evidence that deterministic code already produced. It is never
the source of market truth, and it is never asked open questions like "will XYZ go up?". Every
request sends structured evidence (price, volume, indicators, market/sector context, detected
patterns, historical cases, news, risk flags); the model explains it.

The LLM must not invent prices, volumes, news, historical results, indicators or other financial
facts. Structured-output validation exists specifically to catch this (§Validation).

## Providers

`LLMProvider` interface, with concrete adapters:
```
LLMProvider
  ├── GroqProvider
  └── CerebrasProvider
```
Model choice (e.g. GPT-OSS 120B, Qwen-class models, or others available on these providers) is
never hard-coded; it's selected by the router per task and confirmed against what's currently
available.

## Multiple API keys

The user may register multiple credentials per provider. This is for monitoring usage, respecting
`Retry-After` and rate-limit headers, exponential backoff, temporarily disabling an exhausted
credential, and failing over to another *authorized* provider/model — recording every failover.
It is explicitly **not** a mechanism to route around a provider's rate limits or terms; rotation
for that purpose is disallowed.

## Routing

`LLMRouter` classifies each request by task complexity:

| Tier | Examples | Target model class |
|---|---|---|
| Simple | alert summarization, short explanation, classification | fast/cheap |
| Medium | stock analysis, news interpretation, pattern explanation | medium capability |
| Complex | multi-source research, strategy analysis, deep reports | strongest available |

Routing also weighs provider availability, current quota, latency, token budget, and whether
structured output is supported for the candidate model.

## Structured output & validation

Expected response shape (see DATA_MODEL.md `LLMAnalysis`): `summary`, `observations[]`,
`patterns[]`, `historical_context{}`, `possible_scenarios[]`, `risk_factors[]`,
`invalidation_conditions[]`, `uncertainty[]`, `missing_information[]`.

On validation failure: (1) retry once, (2) try another authorized provider/model, (3) fall back to
deterministic analysis. Malformed LLM output must never crash or stall market monitoring.

## Cost control

Pipeline is `tick → deterministic processing → aggregation → event detection → important event →
optional LLM → Telegram` — never `tick → LLM`. Reusable analysis is cached. Small/fast models
handle simple tasks; large models are reserved for complex ones.

## Deterministic fallback

If every LLM provider is unavailable, DataBroker still collects data, computes indicators, detects
patterns, generates alerts and sends Telegram messages — e.g. "XYZ +4.8%, relative volume 3.2×,
broke 20-day high." No LLM dependency may sit on the critical monitoring path.
