from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.controllers.intraday_screening_controller import list_intraday_screenings
from app.db import get_db
from app.response import api_error, api_success


router = APIRouter()


@router.get("/api/intraday-screenings")
def intraday_screenings(
    request: Request,
    market: str = "all",
    min_market_cap: Decimal = Decimal("200000000000"),
    min_avg_volume: Decimal = Decimal("10000000"),
    interval: str = "5m",
    page: int = 1,
    page_size: int = 50,
    session: Session = Depends(get_db),
):
    request_id = request.state.request_id
    try:
        data = list_intraday_screenings(
            session=session,
            market=market,
            min_market_cap=min_market_cap,
            min_avg_volume=min_avg_volume,
            interval=interval,
            page=page,
            page_size=page_size,
        )
        return api_success(data)
    except Exception as exc:
        request.state.error_message = str(exc)
        return api_error(request_id)
