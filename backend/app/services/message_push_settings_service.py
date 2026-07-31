from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import insert
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.message_push_setting import MessagePushSetting

SETTINGS_ID = 1

MIN_INTERVAL_MINUTES = 10
MAX_INTERVAL_MINUTES = 120
INTERVAL_MINUTES_STEP = 10
DEFAULT_INTERVAL_MINUTES = 60

MIN_MARKET_CAP = Decimal("50000000000")
MAX_MARKET_CAP = Decimal("2000000000000")
MARKET_CAP_STEP = Decimal("50000000000")
DEFAULT_MIN_MARKET_CAP = Decimal("200000000000")

MIN_AVG_VOLUME = Decimal("1000000")
MAX_AVG_VOLUME = Decimal("100000000")
AVG_VOLUME_STEP = Decimal("1000000")
DEFAULT_MIN_AVG_VOLUME = Decimal("10000000")


@dataclass(frozen=True)
class MessagePushSettingsSnapshot:
    interval_minutes: int
    min_market_cap: Decimal
    min_avg_volume: Decimal
    updated_at: datetime | None


def get_message_push_settings(session: Session) -> MessagePushSettingsSnapshot:
    row = session.get(MessagePushSetting, SETTINGS_ID)
    if row is None:
        _create_default_settings_if_missing(session)
        row = session.get(MessagePushSetting, SETTINGS_ID)
        if row is None:
            raise RuntimeError("message push settings singleton was not created")
    return _snapshot_from_row(row)


def save_message_push_settings(
    session: Session, snapshot: MessagePushSettingsSnapshot
) -> MessagePushSettingsSnapshot:
    _validate(snapshot)

    row = session.get(MessagePushSetting, SETTINGS_ID)
    if row is None:
        row = MessagePushSetting(id=SETTINGS_ID)
        session.add(row)

    row.interval_minutes = snapshot.interval_minutes
    row.min_market_cap = snapshot.min_market_cap
    row.min_avg_volume = snapshot.min_avg_volume
    row.updated_at = datetime.now(timezone.utc)

    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(row)
    return _snapshot_from_row(row)


def _validate(snapshot: MessagePushSettingsSnapshot) -> None:
    if (
        isinstance(snapshot.interval_minutes, bool)
        or not isinstance(snapshot.interval_minutes, int)
        or not MIN_INTERVAL_MINUTES <= snapshot.interval_minutes <= MAX_INTERVAL_MINUTES
        or snapshot.interval_minutes % INTERVAL_MINUTES_STEP != 0
    ):
        raise ValueError("interval_minutes must be between 10 and 120 in increments of 10")
    _validate_threshold(
        "min_market_cap", snapshot.min_market_cap, MIN_MARKET_CAP, MAX_MARKET_CAP, MARKET_CAP_STEP
    )
    _validate_threshold(
        "min_avg_volume", snapshot.min_avg_volume, MIN_AVG_VOLUME, MAX_AVG_VOLUME, AVG_VOLUME_STEP
    )


def _validate_threshold(
    name: str, value: Decimal, minimum: Decimal, maximum: Decimal, step: Decimal
) -> None:
    if not isinstance(value, Decimal) or not minimum <= value <= maximum or (value - minimum) % step:
        raise ValueError(f"{name} is out of range or not aligned to its step")


def _create_default_settings_if_missing(session: Session) -> None:
    values = {
        "id": SETTINGS_ID,
        "interval_minutes": DEFAULT_INTERVAL_MINUTES,
        "min_market_cap": DEFAULT_MIN_MARKET_CAP,
        "min_avg_volume": DEFAULT_MIN_AVG_VOLUME,
        "updated_at": datetime.now(timezone.utc),
    }
    dialect_name = session.get_bind().dialect.name
    if dialect_name == "sqlite":
        statement = sqlite_insert(MessagePushSetting).values(**values)
        statement = statement.on_conflict_do_nothing(index_elements=["id"])
    elif dialect_name == "postgresql":
        statement = postgresql_insert(MessagePushSetting).values(**values)
        statement = statement.on_conflict_do_nothing(index_elements=["id"])
    else:
        statement = insert(MessagePushSetting).values(**values)

    try:
        session.execute(statement)
        session.commit()
    except IntegrityError:
        session.rollback()
        if session.get(MessagePushSetting, SETTINGS_ID) is None:
            raise
    except Exception:
        session.rollback()
        raise


def _snapshot_from_row(row: MessagePushSetting) -> MessagePushSettingsSnapshot:
    updated_at = row.updated_at
    if updated_at is not None and updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    snapshot = MessagePushSettingsSnapshot(
        interval_minutes=row.interval_minutes,
        min_market_cap=row.min_market_cap,
        min_avg_volume=row.min_avg_volume,
        updated_at=updated_at,
    )
    _validate(snapshot)
    return snapshot
