from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services.message_push_scheduler import start_message_push, stop_message_push


def test_disabled_message_push_does_not_create_services(monkeypatch):
    monkeypatch.setenv("ENABLE_MESSAGE_PUSH", "false")
    app = SimpleNamespace(state=SimpleNamespace())

    asyncio.run(start_message_push(app))
    asyncio.run(stop_message_push(app))

    assert not hasattr(app.state, "message_push_scheduler")
