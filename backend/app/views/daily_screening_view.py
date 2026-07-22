from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.controllers.daily_screening_controller import list_daily_screenings
from app.db import get_db
from app.response import api_error, api_success


router = APIRouter()


@router.get("/api/daily-screenings")
def daily_screenings(
    request: Request,
    market: str = "all",
    signal_type: str = "all",
    min_market_cap: Decimal = Decimal("200000000000"),
    min_avg_volume: Decimal = Decimal("10000000"),
    page: int = 1,
    page_size: int = 50,
    session: Session = Depends(get_db),
):
    request_id = request.state.request_id
    try:
        data = list_daily_screenings(
            session=session,
            market=market,
            signal_type=signal_type,
            min_market_cap=min_market_cap,
            min_avg_volume=min_avg_volume,
            page=page,
            page_size=page_size,
        )
        return api_success(data)
    except Exception as exc:
        request.state.error_message = str(exc)
        return api_error(request_id)
