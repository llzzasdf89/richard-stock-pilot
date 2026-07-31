from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
import threading

import pytest
from sqlalchemy import create_engine, event, func, select
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


def test_get_rejects_corrupt_persisted_interval(session):
    session.add(
        MessagePushSetting(
            id=1,
            interval_minutes=0,
            min_market_cap=Decimal("200000000000"),
            min_avg_volume=Decimal("10000000"),
            updated_at=datetime.now(timezone.utc),
        )
    )
    session.commit()

    with pytest.raises(ValueError, match="interval_minutes"):
        get_message_push_settings(session)


def test_concurrent_first_reads_return_defaults_and_create_one_row(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'concurrent-settings.db'}",
        connect_args={"timeout": 1},
    )
    Base.metadata.create_all(engine)

    class ConcurrentSession(Session):
        pass

    concurrent_session_factory = sessionmaker(bind=engine, class_=ConcurrentSession)
    start_barrier = threading.Barrier(2)
    flush_barrier = threading.Barrier(2)

    def synchronize_default_inserts(active_session, flush_context, instances):
        if any(
            isinstance(instance, MessagePushSetting)
            for instance in active_session.new
        ):
            flush_barrier.wait(timeout=5)

    event.listen(ConcurrentSession, "before_flush", synchronize_default_inserts)

    def load_defaults():
        start_barrier.wait(timeout=5)
        try:
            with concurrent_session_factory() as active_session:
                return ("ok", get_message_push_settings(active_session))
        except Exception as exc:
            return ("error", type(exc).__name__)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: load_defaults(), range(2)))

        assert [outcome[0] for outcome in outcomes] == ["ok", "ok"], outcomes
        assert all(
            outcome[1].interval_minutes == 60
            and outcome[1].min_market_cap == Decimal("200000000000")
            and outcome[1].min_avg_volume == Decimal("10000000")
            for outcome in outcomes
        )
        with concurrent_session_factory() as active_session:
            assert active_session.scalar(
                select(func.count(MessagePushSetting.id))
            ) == 1
    finally:
        event.remove(ConcurrentSession, "before_flush", synchronize_default_inserts)
        engine.dispose()
