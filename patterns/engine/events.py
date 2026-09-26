"""Important-event detection — the "what changed, is it important" layer (docs §15).

Distinct from pattern detection: an event is a single unusual observation (a volume
spike, a rapid price move); a pattern is a combination of signals that resembles a
named setup. Events can exist without a pattern and vice versa.

Thresholds are explicit constructor parameters (never magic numbers buried in logic)
and should ultimately be sourced from configuration per instrument/universe.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.market import Instrument
from app.domain.patterns import EventCategory, MarketEvent, Severity
from market.analytics.context import MarketContext
from market.analytics.price_volume import PriceVolumeSnapshot


@dataclass(frozen=True)
class EventThresholds:
    rapid_price_change_pct: float = 3.0
    extreme_price_change_pct: float = 7.0
    unusual_relative_volume: float = 2.0
    extreme_relative_volume: float = 4.0
    volume_acceleration_threshold: float = 2.0


def detect_price_events(
    instrument: Instrument,
    snapshot: PriceVolumeSnapshot,
    as_of: datetime,
    thresholds: EventThresholds = EventThresholds(),
) -> list[MarketEvent]:
    events: list[MarketEvent] = []
    change = snapshot.price_change_pct
    if change is None:
        return events

    direction = "increase" if change >= 0 else "decrease"
    magnitude = abs(change)

    if magnitude >= thresholds.extreme_price_change_pct:
        events.append(
            MarketEvent(
                category=EventCategory.PRICE,
                instrument=instrument,
                detected_at=as_of,
                description=f"Extreme price {direction}: {change:.2f}%",
                severity=Severity.CRITICAL,
                source_signals=[f"price_change_pct={change:.2f}"],
            )
        )
    elif magnitude >= thresholds.rapid_price_change_pct:
        events.append(
            MarketEvent(
                category=EventCategory.PRICE,
                instrument=instrument,
                detected_at=as_of,
                description=f"Rapid price {direction}: {change:.2f}%",
                severity=Severity.IMPORTANT,
                source_signals=[f"price_change_pct={change:.2f}"],
            )
        )
    return events


def detect_volume_events(
    instrument: Instrument,
    snapshot: PriceVolumeSnapshot,
    as_of: datetime,
    thresholds: EventThresholds = EventThresholds(),
) -> list[MarketEvent]:
    events: list[MarketEvent] = []
    rel_vol = snapshot.relative_volume

    if rel_vol is not None and rel_vol >= thresholds.extreme_relative_volume:
        events.append(
            MarketEvent(
                category=EventCategory.VOLUME,
                instrument=instrument,
                detected_at=as_of,
                description=f"Extreme relative volume: {rel_vol:.1f}x",
                severity=Severity.CRITICAL,
                source_signals=[f"relative_volume={rel_vol:.2f}"],
            )
        )
    elif rel_vol is not None and rel_vol >= thresholds.unusual_relative_volume:
        events.append(
            MarketEvent(
                category=EventCategory.VOLUME,
                instrument=instrument,
                detected_at=as_of,
                description=f"Unusual relative volume: {rel_vol:.1f}x",
                severity=Severity.WATCH,
                source_signals=[f"relative_volume={rel_vol:.2f}"],
            )
        )

    accel = snapshot.volume_acceleration
    if accel is not None and accel >= thresholds.volume_acceleration_threshold:
        events.append(
            MarketEvent(
                category=EventCategory.VOLUME,
                instrument=instrument,
                detected_at=as_of,
                description=f"Volume accelerating: {accel:.1f}x recent average",
                severity=Severity.WATCH,
                source_signals=[f"volume_acceleration={accel:.2f}"],
            )
        )
    return events


def detect_technical_events(
    instrument: Instrument,
    snapshot: PriceVolumeSnapshot,
    as_of: datetime,
) -> list[MarketEvent]:
    events: list[MarketEvent] = []
    bd = snapshot.breakout_distance_pct
    if bd is not None and bd > 0:
        events.append(
            MarketEvent(
                category=EventCategory.TECHNICAL,
                instrument=instrument,
                detected_at=as_of,
                description=f"Trading above recent 20-bar high by {bd:.2f}%",
                severity=Severity.WATCH,
                source_signals=[f"breakout_distance_pct={bd:.2f}"],
            )
        )
    return events


def detect_market_events(
    instrument: Instrument,
    context: MarketContext,
    as_of: datetime,
    volatility_note_threshold_regime: str = "HIGH_VOLATILITY",
) -> list[MarketEvent]:
    events: list[MarketEvent] = []
    if context.regime.value == volatility_note_threshold_regime:
        events.append(
            MarketEvent(
                category=EventCategory.MARKET,
                instrument=instrument,
                detected_at=as_of,
                description="Broader market is in a high-volatility regime",
                severity=Severity.WATCH,
                source_signals=[f"market_regime={context.regime.value}"],
            )
        )
    return events


def detect_all_events(
    instrument: Instrument,
    snapshot: PriceVolumeSnapshot,
    context: MarketContext,
    as_of: datetime,
    thresholds: EventThresholds = EventThresholds(),
) -> list[MarketEvent]:
    return [
        *detect_price_events(instrument, snapshot, as_of, thresholds),
        *detect_volume_events(instrument, snapshot, as_of, thresholds),
        *detect_technical_events(instrument, snapshot, as_of),
        *detect_market_events(instrument, context, as_of),
    ]
