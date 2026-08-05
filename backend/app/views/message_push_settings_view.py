from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.controllers.message_push_settings_controller import get_settings, update_settings
from app.db import get_db
from app.response import api_error, api_success
from app.services.message_push_settings_service import MessagePushSettingsSnapshot


router = APIRouter()


class MessagePushSettingsUpdate(BaseModel):
    interval_minutes: int = Field(ge=10, le=120, multiple_of=10)
    min_market_cap: Decimal = Field(
        ge=Decimal("50000000000"),
        le=Decimal("2000000000000"),
        multiple_of=Decimal("50000000000"),
    )
    min_avg_volume: Decimal = Field(
        ge=Decimal("1000000"),
        le=Decimal("100000000"),
        multiple_of=Decimal("1000000"),
    )


@router.get("/api/message-push-settings")
def message_push_settings(request: Request, session: Session = Depends(get_db)):
    request_id = request.state.request_id
    try:
        return api_success(_serialize(get_settings(session)))
    except Exception as exc:
        request.state.error_message = str(exc)
        return api_error(request_id)


@router.put("/api/message-push-settings")
def save_message_push_settings_view(
    payload: MessagePushSettingsUpdate,
    request: Request,
    session: Session = Depends(get_db),
):
    request_id = request.state.request_id
    try:
        settings = update_settings(
            session=session,
            interval_minutes=payload.interval_minutes,
            min_market_cap=payload.min_market_cap,
            min_avg_volume=payload.min_avg_volume,
        )
        scheduler = getattr(request.app.state, "message_push_scheduler", None)
        if scheduler is not None:
            scheduler.notify_settings_changed()
        return api_success(_serialize(settings))
    except Exception as exc:
        request.state.error_message = str(exc)
        return api_error(request_id)


def _serialize(settings: MessagePushSettingsSnapshot) -> dict[str, int | str | None]:
    return {
        "interval_minutes": settings.interval_minutes,
        "min_market_cap": int(settings.min_market_cap),
        "min_avg_volume": int(settings.min_avg_volume),
        "updated_at": _serialize_datetime(settings.updated_at),
    }


def _serialize_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
