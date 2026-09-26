"""Market/sector context — a stock is never analyzed in isolation.

docs/ARCHITECTURE.md example: "Stock +5%, Market +2%" is a different situation than
"Stock +5%, Market -1%". This module preserves that context and computes relative
strength so pattern detectors and alerts can carry it as evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.domain.market import IndexSnapshot


class MarketRegime(str, Enum):
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    NEUTRAL = "NEUTRAL"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"


@dataclass(frozen=True)
class MarketContext:
    market_index: IndexSnapshot
    sector_index: IndexSnapshot | None
    stock_change_pct: float
    regime: MarketRegime

    @property
    def relative_strength_vs_market(self) -> float:
        """Stock change minus market change — positive means outperforming the market."""
        return self.stock_change_pct - self.market_index.change_pct

    @property
    def relative_strength_vs_sector(self) -> float | None:
        if self.sector_index is None:
            return None
        return self.stock_change_pct - self.sector_index.change_pct

    @property
    def market_confirms_move(self) -> bool:
        """True when the stock's move is in the same direction as the market
        (a momentum/breakout pattern is more credible with market confirmation)."""
        return (self.stock_change_pct >= 0) == (self.market_index.change_pct >= 0)

    @property
    def sector_confirms_move(self) -> bool | None:
        if self.sector_index is None:
            return None
        return (self.stock_change_pct >= 0) == (self.sector_index.change_pct >= 0)


def classify_regime(
    market_change_pct: float, market_volatility: float | None, vol_threshold: float = 1.5
) -> MarketRegime:
    """Simple, explainable regime classification — not a model.

    A more sophisticated regime detector belongs in ml/ (see docs/ML_ARCHITECTURE.md);
    this deterministic version keeps the system functional without one.
    """
    if market_volatility is not None and market_volatility >= vol_threshold:
        return MarketRegime.HIGH_VOLATILITY
    if market_change_pct >= 0.5:
        return MarketRegime.RISK_ON
    if market_change_pct <= -0.5:
        return MarketRegime.RISK_OFF
    return MarketRegime.NEUTRAL


def build_context(
    stock_change_pct: float,
    market_index: IndexSnapshot,
    sector_index: IndexSnapshot | None,
    market_volatility: float | None = None,
) -> MarketContext:
    regime = classify_regime(market_index.change_pct, market_volatility)
    return MarketContext(
        market_index=market_index,
        sector_index=sector_index,
        stock_change_pct=stock_change_pct,
        regime=regime,
    )
