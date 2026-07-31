from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import MessagePushSetting
from app.models.base import Base
from app.services.message_push_settings_service import (
    MessagePushSettingsSnapshot,
    get_message_push_settings,
    save_message_push_settings,
)


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'settings.db'}")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)
    engine.dispose()


@pytest.fixture
def session(session_factory):
    with session_factory() as active_session:
        yield active_session


def valid_snapshot(**overrides):
    values = {
        "interval_minutes": 60,
        "min_market_cap": Decimal("200000000000"),
        "min_avg_volume": Decimal("10000000"),
        "updated_at": None,
    }
    values.update(overrides)
    return MessagePushSettingsSnapshot(**values)


def test_get_creates_default_singleton(session):
    settings = get_message_push_settings(session)

    assert settings == MessagePushSettingsSnapshot(
        interval_minutes=60,
        min_market_cap=Decimal("200000000000"),
        min_avg_volume=Decimal("10000000"),
        updated_at=settings.updated_at,
    )
    assert session.scalar(select(func.count(MessagePushSetting.id))) == 1


def test_save_survives_a_new_session(session_factory):
    with session_factory() as session:
        save_message_push_settings(
            session,
            MessagePushSettingsSnapshot(
                interval_minutes=30,
                min_market_cap=Decimal("250000000000"),
                min_avg_volume=Decimal("12000000"),
                updated_at=None,
            ),
        )

    with session_factory() as session:
        saved = get_message_push_settings(session)

    assert saved.interval_minutes == 30
    assert saved.min_market_cap == Decimal("250000000000")
    assert saved.min_avg_volume == Decimal("12000000")


@pytest.mark.parametrize("interval", [0, 11, 130])
def test_rejects_invalid_interval(session, interval):
    with pytest.raises(ValueError):
        save_message_push_settings(session, valid_snapshot(interval_minutes=interval))


@pytest.mark.parametrize(
    ("min_market_cap", "min_avg_volume"),
    [
        (Decimal("49999999999"), Decimal("10000000")),
        (Decimal("525000000000"), Decimal("10000000")),
        (Decimal("2050000000000"), Decimal("10000000")),
        (Decimal("200000000000"), Decimal("999999")),
        (Decimal("200000000000"), Decimal("10500000")),
        (Decimal("200000000000"), Decimal("101000000")),
    ],
)
def test_rejects_out_of_range_or_misaligned_thresholds(
    session, min_market_cap, min_avg_volume
):
    with pytest.raises(ValueError):
        save_message_push_settings(
            session,
            valid_snapshot(
                min_market_cap=min_market_cap,
                min_avg_volume=min_avg_volume,
            ),
        )
