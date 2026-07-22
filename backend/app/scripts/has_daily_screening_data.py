from __future__ import annotations

import argparse
from datetime import date

from app.db import SessionLocal, init_db
from app.services.daily_sync_service import has_daily_screening_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Check whether daily screening data exists.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Trade date in YYYY-MM-DD")
    args = parser.parse_args()

    init_db()
    session = SessionLocal()
    try:
        exists = has_daily_screening_data(session, date.fromisoformat(args.date))
    finally:
        session.close()
    raise SystemExit(0 if exists else 1)


if __name__ == "__main__":
    main()
