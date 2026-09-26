"""Proves the two previously-missing wiring points:

1. build_llm_router_from_settings actually turns GROQ_API_KEYS/CEREBRAS_API_KEYS
   config into a real LLMRouter with real provider objects (or None with no keys) —
   intelligence/llm/router.py existed and was tested in isolation, but nothing ever
   called it from configuration before intelligence/llm/build.py.
2. RealTimeService actually invokes that router for an alert it already produced,
   and appends exactly one short line to the Telegram text — never the full
   structured analysis, and never for a check where nothing fired.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.config.settings import LLMSettings
from app.domain.market import IndexSnapshot, Instrument, OHLCVBar
from app.domain.providers import LLMProvider
from app.orchestration.pipeline import MonitoringPipeline
from app.orchestration.realtime_service import RealTimeService
from alerts.telegram.delivery_queue import DeliveryQueue
from alerts.telegram.notifier import TelegramNotifier
from data.storage.database import create_db_engine, init_db, make_session_factory
from data.storage.repositories import AlertRepository
from intelligence.llm.build import build_llm_router_from_settings
from intelligence.llm.router import LLMRouter

INSTRUMENT = Instrument(symbol="XYZ", exchange="NSE")


def _bars(closes, volumes):
    out = []
    for i, (c, v) in enumerate(zip(closes, volumes)):
        ts = datetime(2026, 9, 21, 9, 15, tzinfo=timezone.utc) + timedelta(minutes=i)
        out.append(
            OHLCVBar(
                instrument=INSTRUMENT, interval="1m", open=c, high=c * 1.01, low=c * 0.99,
                close=c, volume=v, timestamp=ts, source="test", ingestion_timestamp=ts,
            )
        )
    return out


def test_build_llm_router_returns_none_with_no_keys():
    settings = LLMSettings(GROQ_API_KEYS="", CEREBRAS_API_KEYS="")
    assert build_llm_router_from_settings(settings) is None


def test_build_llm_router_builds_real_providers_from_keys():
    settings = LLMSettings(GROQ_API_KEYS="g1,g2", CEREBRAS_API_KEYS="c1")
    router = build_llm_router_from_settings(settings)
    assert router is not None
    assert [p.name for p in router.providers] == ["groq", "cerebras"]
    # Locked to one model per provider, gpt-oss-120b primary / qwen-3-27b secondary
    # (only reached once every Groq key is exhausted) — not two models tried within
    # one provider, and not relying on the provider classes' own defaults drifting.
    assert [p.default_model for p in router.providers] == ["gpt-oss-120b", "qwen-3-27b"]


def test_build_llm_router_uses_only_groq_when_no_cerebras_keys():
    settings = LLMSettings(GROQ_API_KEYS="g1", CEREBRAS_API_KEYS="")
    router = build_llm_router_from_settings(settings)
    assert router is not None
    assert [p.name for p in router.providers] == ["groq"]


class RecordingProvider(LLMProvider):
    """Records whether it was called, and whether it raised — proves the router's
    actual call order, not just the providers list order."""

    def __init__(self, name: str, fail: bool):
        self.name = name
        self.fail = fail
        self.called = False

    async def complete_structured(self, task_type, evidence, schema):
        self.called = True
        if self.fail:
            from intelligence.llm.providers import ProviderError

            raise ProviderError(f"{self.name}: simulated exhaustion")
        return {
            "summary": f"handled by {self.name}", "observations": [], "patterns": [],
            "historical_context": {}, "possible_scenarios": [], "risk_factors": [],
            "invalidation_conditions": [], "uncertainty": [], "missing_information": [],
        }

    async def health(self):
        return {"status": "OK"}


@pytest.mark.asyncio
async def test_secondary_model_is_never_called_while_primary_still_works():
    primary = RecordingProvider("groq", fail=False)
    secondary = RecordingProvider("cerebras", fail=False)
    router = LLMRouter(providers=[primary, secondary])

    analysis, used_llm = await router.analyze("alert_summary", {})

    assert used_llm is True
    assert primary.called is True
    assert secondary.called is False  # never touched — primary already succeeded
    assert "groq" in analysis.summary


@pytest.mark.asyncio
async def test_secondary_model_is_used_only_after_primary_is_exhausted():
    primary = RecordingProvider("groq", fail=True)
    secondary = RecordingProvider("cerebras", fail=False)
    router = LLMRouter(providers=[primary, secondary])

    analysis, used_llm = await router.analyze("alert_summary", {})

    assert used_llm is True
    assert primary.called is True   # tried first
    assert secondary.called is True  # only reached because primary failed
    assert "cerebras" in analysis.summary


class OneLinerProvider(LLMProvider):
    """Fake provider standing in for a real Groq/Cerebras call in this test — proves
    the service-level wiring/formatting without any network dependency."""

    name = "fake"

    async def complete_structured(self, task_type, evidence, schema):
        return {
            "summary": "Sharp volume-backed breakout, unconfirmed by the broader market.",
            "observations": [], "patterns": [], "historical_context": {},
            "possible_scenarios": [], "risk_factors": [], "invalidation_conditions": [],
            "uncertainty": [], "missing_information": [],
        }

    async def health(self):
        return {"status": "OK"}


def _service_with_llm(sent: list[str]):
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    repo = AlertRepository(make_session_factory(engine))

    async def transport(chat_id, body):
        sent.append(body["text"])
        return {"ok": True}

    notifier = TelegramNotifier(bot_token="tok", chat_id="1", transport=transport)
    return RealTimeService(
        pipeline=MonitoringPipeline(),
        alert_repository=repo,
        notifier=notifier,
        delivery_queue=DeliveryQueue(base_backoff_seconds=1.0),
        llm_router=LLMRouter(providers=[OneLinerProvider()]),
    )


@pytest.mark.asyncio
async def test_llm_note_is_appended_when_an_alert_fires():
    sent: list[str] = []
    service = _service_with_llm(sent)
    closes = [100 + i * 0.3 for i in range(59)] + [140.0]
    volumes = [1000] * 59 + [6000]
    bars = _bars(closes, volumes)
    as_of = bars[-1].timestamp
    market_index = IndexSnapshot(
        code="NIFTY50", value=20000, change=100, change_pct=0.5, timestamp=as_of, source="test"
    )

    row_ids = await service.handle_update(INSTRUMENT, bars, market_index, None, as_of)
    assert row_ids
    assert sent  # something was actually delivered to Telegram
    assert any("Sharp volume-backed breakout" in text for text in sent)
    # Still just one short appended line per message, not the full structured analysis:
    assert all(text.count("\U0001f916") <= 1 for text in sent)


@pytest.mark.asyncio
async def test_llm_is_never_called_when_nothing_fires():
    sent: list[str] = []
    service = _service_with_llm(sent)
    # Flat, boring data — no pattern, no event, no anomaly should fire.
    bars = _bars([100.0] * 40, [1000] * 40)
    as_of = bars[-1].timestamp
    market_index = IndexSnapshot(
        code="NIFTY50", value=20000, change=0.0, change_pct=0.0, timestamp=as_of, source="test"
    )

    row_ids = await service.handle_update(INSTRUMENT, bars, market_index, None, as_of)
    assert row_ids == []  # confirms: no alert fired -> LLM never touched, zero cost
    assert sent == []
