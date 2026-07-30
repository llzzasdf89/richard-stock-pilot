from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Any
from zoneinfo import ZoneInfo

from app.config import message_push_enabled
from app.services.longbridge_service import LongbridgeService
from app.services.message_push_cache_service import MessagePushCacheService
from app.services.message_push_scan_service import MessagePushScanService
from app.services.pushplus_message_service import (
    PushPlusConfigurationError,
    PushPlusMessageService,
)


logger = logging.getLogger(__name__)
CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")


def seconds_until_next_china_hour(now: datetime | None = None) -> float:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=CHINA_TIMEZONE)
    china_now = current.astimezone(CHINA_TIMEZONE)
    next_hour = china_now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return (next_hour - china_now).total_seconds()


class MessagePushScheduler:
    def __init__(self, scanner: MessagePushScanService) -> None:
        self.scanner = scanner
        self._round_lock = asyncio.Lock()

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
        while True:
            await asyncio.sleep(seconds_until_next_china_hour())
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
    scheduler = MessagePushScheduler(scanner)
    app.state.message_push_cache_service = cache_service
    app.state.message_push_scheduler = scheduler
    app.state.message_push_task = asyncio.create_task(
        scheduler.run_forever(), name="message-push-hourly"
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
