from __future__ import annotations

import asyncio
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace

from app.services.message_push_settings_service import MessagePushSettingsSnapshot
import app.services.message_push_scheduler as scheduler_module
from app.services.message_push_scheduler import start_message_push, stop_message_push


def test_disabled_message_push_does_not_create_services(monkeypatch):
    monkeypatch.setenv("ENABLE_MESSAGE_PUSH", "false")
    app = SimpleNamespace(state=SimpleNamespace())

    asyncio.run(start_message_push(app))
    asyncio.run(stop_message_push(app))

    assert not hasattr(app.state, "message_push_scheduler")


def test_enabled_message_push_loads_settings_from_app_session_factory(monkeypatch):
    session = object()
    opened_sessions = []
    captured_settings_loader = None

    @contextmanager
    def session_factory():
        opened_sessions.append(session)
        yield session

    def get_settings(active_session):
        assert active_session is session
        return MessagePushSettingsSnapshot(
            interval_minutes=30,
            min_market_cap=Decimal("200000000000"),
            min_avg_volume=Decimal("10000000"),
            updated_at=None,
        )

    class FakeSenderFactory:
        @classmethod
        def from_environment(cls):
            return object()

    class FakeCache:
        def __init__(self, longbridge):
            pass

        def is_trading_day(self, market, now):
            return False

    class FakeScheduler:
        def __init__(self, scanner, settings_loader):
            nonlocal captured_settings_loader
            captured_settings_loader = settings_loader

        async def run_forever(self):
            await asyncio.Event().wait()

    monkeypatch.setenv("ENABLE_MESSAGE_PUSH", "true")
    monkeypatch.setattr(scheduler_module, "PushPlusMessageService", FakeSenderFactory)
    monkeypatch.setattr(scheduler_module, "LongbridgeService", lambda: object())
    monkeypatch.setattr(scheduler_module, "MessagePushCacheService", FakeCache)
    monkeypatch.setattr(scheduler_module, "MessagePushScanService", lambda *args: object())
    monkeypatch.setattr(scheduler_module, "MessagePushScheduler", FakeScheduler)
    monkeypatch.setattr(scheduler_module, "get_message_push_settings", get_settings)
    app = SimpleNamespace(state=SimpleNamespace(session_factory=session_factory))

    async def scenario():
        await start_message_push(app)
        try:
            loaded = captured_settings_loader()
        finally:
            await stop_message_push(app)
        return loaded

    loaded = asyncio.run(scenario())

    assert opened_sessions == [session]
    assert loaded.interval_minutes == 30
