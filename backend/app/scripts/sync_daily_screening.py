from __future__ import annotations

import argparse

from app.db import SessionLocal, init_db
from app.services.daily_sync_service import sync_daily_screening
from app.services.longbridge_service import LongbridgeService


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync daily screening data from Longbridge.")
    parser.add_argument("--symbols", nargs="+", required=True, help="Symbols like AAPL.US 700.HK")
    parser.add_argument("--bar-count", type=int, default=60)
    args = parser.parse_args()

    init_db()
    session = SessionLocal()
    try:
        result = sync_daily_screening(
            session,
            symbols=args.symbols,
            longbridge=LongbridgeService(),
            bar_count=args.bar_count,
        )
    finally:
        session.close()
    print(result)


if __name__ == "__main__":
    main()
