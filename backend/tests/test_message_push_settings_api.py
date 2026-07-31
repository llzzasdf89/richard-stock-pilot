import threading

import pytest

from app.main import app
from tests.test_api import build_client


class FakeScheduler:
    def __init__(self) -> None:
        self.settings_changed = threading.Event()

    def notify_settings_changed(self) -> None:
        self.settings_changed.set()


@pytest.fixture
def client():
    test_client, _ = build_client()
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def scheduler():
    fake_scheduler = FakeScheduler()
    app.state.message_push_scheduler = fake_scheduler
    yield fake_scheduler
    del app.state.message_push_scheduler


def test_get_returns_persisted_settings(client):
    body = client.get("/api/message-push-settings").json()

    assert body["success"] is True
    assert body["data"]["interval_minutes"] == 60
    assert body["data"]["min_market_cap"] == 200000000000


def test_put_saves_full_settings_and_notifies_scheduler(client, scheduler):
    body = client.put(
        "/api/message-push-settings",
        json={
            "interval_minutes": 30,
            "min_market_cap": 250000000000,
            "min_avg_volume": 12000000,
        },
    ).json()

    assert body["success"] is True
    assert body["data"]["interval_minutes"] == 30
    assert scheduler.settings_changed.is_set()


def test_put_rejects_off_step_value(client):
    body = client.put(
        "/api/message-push-settings",
        json={
            "interval_minutes": 35,
            "min_market_cap": 250000000000,
            "min_avg_volume": 12000000,
        },
    ).json()

    assert body["success"] is False
