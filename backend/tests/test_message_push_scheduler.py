from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.message_push_scheduler import (
    MessagePushScheduler,
    seconds_until_next_china_hour,
)


def test_seconds_until_next_china_hour():
    now = datetime(2026, 7, 30, 10, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert seconds_until_next_china_hour(now) == 2670


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
        scheduler = MessagePushScheduler(scanner)
        first = asyncio.create_task(scheduler.run_once_if_idle())
        await asyncio.sleep(0)
        assert await scheduler.run_once_if_idle() is False
        scanner.release.set()
        await first
        assert scanner.calls == 1

    asyncio.run(scenario())
