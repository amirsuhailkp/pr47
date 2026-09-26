"""Scans the real NSE universe for candidates worth investigating (docs §20's
Candidate Discovery Engine), using the same free/testing providers as
scripts/run_local_test.py.

Usage:
    python -m scripts.discover_candidates                       # swing, first 40 symbols
    python -m scripts.discover_candidates --strategy scalping --limit 20
    python -m scripts.discover_candidates --limit 200            # scan more (slower — one
                                                                   # yfinance call per symbol)

What it does:
    1. Fetches the full free NSE main-board equity list (~2,600 symbols, SME already
       excluded — data/providers/nse_universe_provider.py)
    2. Takes the first `--limit` symbols (a real scan of all ~2,600 would be slow and
       yfinance-rate-limit-prone for a free testing setup — raise --limit if you want
       to scan more, or wire in a real broker's bulk quote endpoint later)
    3. For each: backfills bars, applies the price/liquidity/data-quality universe
       filter (market/universe/selection.py), then runs the chosen strategy's
       pattern/event detection
    4. Ranks whatever surfaces (opportunity/ranking/rank.py) and prints the top
       candidates with their full reasons/risks — never a bare score

This is a batch scan, not a live monitor — run it whenever you want a fresh look at
"what's interesting right now" across the universe, rather than checking named symbols.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from app.config.settings import get_settings
from data.providers.nse_universe_provider import NseUniverseProvider, httpx_fetch_csv
from data.providers.yfinance_provider import YFinanceHistoricalProvider, yfinance_fetch
from opportunity.discovery.engine import CandidateDiscoveryEngine
from opportunity.ranking.rank import rank_candidates
from market.strategies.registry import STRATEGIES, get_strategy
from scripts.run_local_test import NIFTY_INDEX, _fetch_index_snapshot


async def main(strategy_name: str, limit: int, top_n: int) -> None:
    settings = get_settings()
    profile = get_strategy(strategy_name)

    universe_provider = NseUniverseProvider(httpx_fetch_csv)
    print("Fetching NSE main-board equity list...")
    universe = await universe_provider.get_universe()
    print(f"Universe: {len(universe)} symbols total, scanning first {limit}")

    historical_provider = YFinanceHistoricalProvider(yfinance_fetch)
    market_index = await _fetch_index_snapshot(historical_provider, profile)
    print(f"NIFTY50 change: {market_index.change_pct:+.2f}%")

    engine = CandidateDiscoveryEngine(historical_provider, settings.market)
    as_of = datetime.now(timezone.utc)
    start = as_of - timedelta(days=profile.lookback_days)

    result = await engine.discover(
        universe, profile, market_index, as_of, start, max_instruments=limit
    )

    print(
        f"\nScanned {result.stats.scanned} | "
        f"insufficient history: {result.stats.insufficient_history} | "
        f"failed universe filter: {result.stats.failed_universe_filter} | "
        f"fetch errors: {result.stats.fetch_errors} | "
        f"candidates: {result.stats.candidates_found}"
    )

    ranked = rank_candidates(result.candidates)
    print(f"\nTop {min(top_n, len(ranked))} candidates ({profile.definition.name}):")
    for rc in ranked[:top_n]:
        ev = rc.evidence
        print(f"\n=== {ev.instrument.symbol} (score {rc.score.total:.2f}) ===")
        print("Reasons:")
        for r in ev.reasons:
            print(f"  + {r}")
        if ev.risks:
            print("Risks:")
            for r in ev.risks:
                print(f"  - {r}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan the NSE universe for candidates.")
    parser.add_argument("--strategy", choices=sorted(STRATEGIES), default="swing")
    parser.add_argument("--limit", type=int, default=40, help="how many symbols to scan")
    parser.add_argument("--top", type=int, default=10, help="how many ranked candidates to print")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(args.strategy, args.limit, args.top))
