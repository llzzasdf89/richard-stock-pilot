from __future__ import annotations

import argparse
from decimal import Decimal

from app.db import SessionLocal, init_db
from app.services.daily_sync_service import sync_daily_screening
from app.services.longbridge_service import LongbridgeService


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync daily screening data from Longbridge.")
    parser.add_argument("--symbols", nargs="*", help="Symbols like AAPL.US 700.HK")
    parser.add_argument("--markets", nargs="+", default=["US", "HK"], choices=["US", "HK"])
    parser.add_argument("--min-market-cap", type=Decimal, default=Decimal("50000000000"))
    parser.add_argument("--min-avg-volume", type=Decimal, default=Decimal("1000000"))
    parser.add_argument("--bar-count", type=int, default=60)
    args = parser.parse_args()

    init_db()
    provider = LongbridgeService()
    symbols = args.symbols or [
        security.symbol
        for market in args.markets
        for security in provider.screen_securities(
            market=market,
            min_market_cap=args.min_market_cap,
            min_avg_volume=args.min_avg_volume,
        )
    ]
    if not symbols:
        raise ValueError("no symbols available for daily screening sync")

    session = SessionLocal()
    try:
        result = sync_daily_screening(
            session,
            symbols=symbols,
            longbridge=provider,
            bar_count=args.bar_count,
        )
    finally:
        session.close()
    print(result)


if __name__ == "__main__":
    main()
