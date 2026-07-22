from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.services.screening_service import get_daily_screenings


def list_daily_screenings(
    session: Session,
    market: str = "all",
    signal_type: str = "all",
    min_market_cap: Decimal = Decimal("200000000000"),
    min_avg_volume: Decimal = Decimal("10000000"),
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    return get_daily_screenings(
        session=session,
        market=market,
        signal_type=signal_type,
        min_market_cap=min_market_cap,
        min_avg_volume=min_avg_volume,
        page=page,
        page_size=page_size,
    )
