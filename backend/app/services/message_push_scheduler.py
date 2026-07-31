from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import math
from collections.abc import Awaitable, Callable
from typing import Any, Literal
from zoneinfo import ZoneInfo

from app.config import message_push_enabled
from app.services.longbridge_service import LongbridgeService
from app.services.message_push_cache_service import MessagePushCacheService
from app.services.message_push_scan_service import MessagePushScanService
from app.services.message_push_settings_service import (
    MessagePushSettingsSnapshot,
    get_message_push_settings,
)
from app.services.pushplus_message_service import (
    PushPlusConfigurationError,
    PushPlusMessageService,
)


logger = logging.getLogger(__name__)
CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")
WaitResult = Literal["boundary", "settings_changed"]


def seconds_until_next_china_boundary(
    interval_minutes: int, now: datetime | None = None
) -> float:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=CHINA_TIMEZONE)
    china_now = current.astimezone(CHINA_TIMEZONE)
    midnight = china_now.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed_minutes = (china_now - midnight).total_seconds() / 60
    boundary_index = math.floor(elapsed_minutes / interval_minutes) + 1
    next_boundary = midnight + timedelta(minutes=boundary_index * interval_minutes)
    return (next_boundary - china_now).total_seconds()


async def _wait_for_next(
    delay: float, settings_changed: asyncio.Event
) -> WaitResult:
    boundary_task = asyncio.create_task(asyncio.sleep(delay))
    settings_task = asyncio.create_task(settings_changed.wait())
    try:
        done, _ = await asyncio.wait(
            (boundary_task, settings_task),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if settings_task in done:
            return "settings_changed"
        return "boundary"
    finally:
        for task in (boundary_task, settings_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(boundary_task, settings_task, return_exceptions=True)


class MessagePushScheduler:
    def __init__(
        self,
        scanner: MessagePushScanService,
        settings_loader: Callable[[], MessagePushSettingsSnapshot],
        wait_for_next: Callable[
            [float, asyncio.Event], Awaitable[WaitResult]
        ] = _wait_for_next,
    ) -> None:
        self.scanner = scanner
        self.settings_loader = settings_loader
        self.wait_for_next = wait_for_next
        self.settings_changed = asyncio.Event()
        self._round_lock = asyncio.Lock()
        try:
            self._event_loop = asyncio.get_running_loop()
        except RuntimeError:
            self._event_loop = None

    def notify_settings_changed(self) -> None:
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if self._event_loop is not None and running_loop is not self._event_loop:
            self._event_loop.call_soon_threadsafe(self.settings_changed.set)
            return
        self.settings_changed.set()

    async def run_once_if_idle(self) -> bool:
        if self._round_lock.locked():
            logger.warning("message_push_round result=skipped reason=previous_round_running")
            return False
        async with self._round_lock:
            try:
                await self.scanner.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("message_push_round result=error")
            return True

    async def run_forever(self) -> None:
        self._event_loop = asyncio.get_running_loop()
        while True:
            settings = self.settings_loader()
            delay = seconds_until_next_china_boundary(settings.interval_minutes)
            wait_result = await self.wait_for_next(delay, self.settings_changed)
            if wait_result == "settings_changed":
                self.settings_changed.clear()
                continue
            await self.run_once_if_idle()


async def start_message_push(app: Any) -> None:
    if not message_push_enabled():
        return
    try:
        sender = PushPlusMessageService.from_environment()
    except PushPlusConfigurationError as exc:
        logger.error("message_push_start result=disabled error=%s", exc)
        return

    longbridge = LongbridgeService()
    cache_service = MessagePushCacheService(longbridge)
    now = datetime.now(timezone.utc)
    for market in ("US", "HK"):
        try:
            if cache_service.is_trading_day(market, now):
                await cache_service.prepare_market(market, now)
        except Exception:
            logger.exception("message_push_start market=%s result=error", market)

    scanner = MessagePushScanService(cache_service, longbridge, sender)
    session_factory = app.state.session_factory

    def load_settings() -> MessagePushSettingsSnapshot:
        with session_factory() as session:
            return get_message_push_settings(session)

    scheduler = MessagePushScheduler(scanner, settings_loader=load_settings)
    app.state.message_push_cache_service = cache_service
    app.state.message_push_scheduler = scheduler
    app.state.message_push_task = asyncio.create_task(
        scheduler.run_forever(), name="message-push-scheduler"
    )
    logger.info("message_push_start result=success")


async def stop_message_push(app: Any) -> None:
    task = getattr(app.state, "message_push_task", None)
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    logger.info("message_push_stop result=success")
