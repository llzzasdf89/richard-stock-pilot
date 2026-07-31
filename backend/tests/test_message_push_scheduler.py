from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
import threading

import pytest

import app.services.message_push_scheduler as scheduler_module
from app.services.message_push_scheduler import CHINA_TIMEZONE, MessagePushScheduler
from app.services.message_push_settings_service import MessagePushSettingsSnapshot


@pytest.mark.parametrize(
    ("now", "interval", "seconds"),
    [
        (datetime(2026, 7, 30, 10, 15, 30, tzinfo=CHINA_TIMEZONE), 10, 270),
        (datetime(2026, 7, 30, 10, 15, 30, tzinfo=CHINA_TIMEZONE), 30, 870),
        (datetime(2026, 7, 30, 10, 0, 0, tzinfo=CHINA_TIMEZONE), 60, 3600),
        (datetime(2026, 7, 30, 10, 15, 30, tzinfo=CHINA_TIMEZONE), 120, 6270),
    ],
)
def test_seconds_until_next_china_boundary(now, interval, seconds):
    assert scheduler_module.seconds_until_next_china_boundary(interval, now) == seconds


def snapshot(interval_minutes: int) -> MessagePushSettingsSnapshot:
    return MessagePushSettingsSnapshot(
        interval_minutes=interval_minutes,
        min_market_cap=Decimal("200000000000"),
        min_avg_volume=Decimal("10000000"),
        updated_at=None,
    )


class RecordingScanner:
    def __init__(self):
        self.calls = 0

    async def run_once(self):
        self.calls += 1


def test_settings_change_wakes_scheduler_without_scanning():
    scanner = RecordingScanner()
    scheduler = MessagePushScheduler(scanner, settings_loader=lambda: snapshot(60))

    assert scheduler.settings_changed.is_set() is False
    scheduler.notify_settings_changed()

    assert scheduler.settings_changed.is_set() is True
    assert scanner.calls == 0


def test_settings_change_recomputes_boundary_without_scanning():
    async def scenario():
        scanner = CancellingScanner()
        loaded_intervals = iter((60, 30))
        loader_calls = []
        wait_results = iter(("settings_changed", "boundary"))

        def load_settings():
            interval = next(loaded_intervals)
            loader_calls.append(interval)
            return snapshot(interval)

        async def wait_for_next(delay, settings_changed):
            return next(wait_results)

        scheduler = MessagePushScheduler(
            scanner,
            settings_loader=load_settings,
            wait_for_next=wait_for_next,
        )
        scheduler.notify_settings_changed()

        with pytest.raises(asyncio.CancelledError):
            await scheduler.run_forever()

        assert loader_calls == [60, 30]
        assert scanner.calls == 1
        assert scheduler.settings_changed.is_set() is False

    asyncio.run(scenario())


def test_settings_change_from_worker_thread_wakes_scheduler_on_its_event_loop():
    async def scenario():
        class ThreadBoundEvent:
            def __init__(self):
                self.owner_thread = threading.get_ident()
                self.event = asyncio.Event()

            def is_set(self):
                return self.event.is_set()

            def set(self):
                if threading.get_ident() != self.owner_thread:
                    raise RuntimeError("event set outside its event-loop thread")
                self.event.set()

            def clear(self):
                self.event.clear()

            async def wait(self):
                await self.event.wait()

        scanner = RecordingScanner()
        first_wait_started = asyncio.Event()
        second_settings_load = asyncio.Event()
        loader_calls = 0
        notification_errors = []

        def load_settings():
            nonlocal loader_calls
            loader_calls += 1
            if loader_calls == 2:
                second_settings_load.set()
            return snapshot(60)

        async def wait_for_settings_change(delay, settings_changed):
            first_wait_started.set()
            await settings_changed.wait()
            return "settings_changed"

        scheduler = MessagePushScheduler(
            scanner,
            settings_loader=load_settings,
            wait_for_next=wait_for_settings_change,
        )
        scheduler.settings_changed = ThreadBoundEvent()
        scheduler_task = asyncio.create_task(scheduler.run_forever())
        await first_wait_started.wait()

        def notify_from_worker():
            try:
                scheduler.notify_settings_changed()
            except Exception as exc:
                notification_errors.append(exc)

        worker = threading.Thread(target=notify_from_worker)
        worker.start()
        worker.join()

        if notification_errors:
            scheduler_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await scheduler_task
            assert notification_errors == []

        try:
            await asyncio.wait_for(second_settings_load.wait(), timeout=1)
        finally:
            scheduler_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await scheduler_task

        assert notification_errors == []
        assert loader_calls == 2
        assert scanner.calls == 0

    asyncio.run(scenario())


class SlowScanner:
    def __init__(self):
        self.calls = 0
        self.release = asyncio.Event()

    async def run_once(self):
        self.calls += 1
        await self.release.wait()


def test_scheduler_skips_overlapping_round():
    async def scenario():
        scanner = SlowScanner()
        scheduler = MessagePushScheduler(scanner, settings_loader=lambda: snapshot(60))
        first = asyncio.create_task(scheduler.run_once_if_idle())
        await asyncio.sleep(0)
        assert await scheduler.run_once_if_idle() is False
        scanner.release.set()
        await first
        assert scanner.calls == 1

    asyncio.run(scenario())


class CancellingScanner:
    def __init__(self):
        self.calls = 0

    async def run_once(self):
        self.calls += 1
        raise asyncio.CancelledError
