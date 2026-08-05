from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.services.message_push_settings_service import (
    MessagePushSettingsSnapshot,
    get_message_push_settings,
    save_message_push_settings,
)


def get_settings(session: Session) -> MessagePushSettingsSnapshot:
    return get_message_push_settings(session)


def update_settings(
    session: Session,
    interval_minutes: int,
    min_market_cap: Decimal,
    min_avg_volume: Decimal,
) -> MessagePushSettingsSnapshot:
    return save_message_push_settings(
        session,
        MessagePushSettingsSnapshot(
            interval_minutes=interval_minutes,
            min_market_cap=min_market_cap,
            min_avg_volume=min_avg_volume,
            updated_at=None,
        ),
    )
