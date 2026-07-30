from __future__ import annotations

import asyncio
from datetime import date, datetime
from decimal import Decimal
import logging
import time
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app.services.longbridge_service import LongbridgeService, MarketDataBar, Security


logger = logging.getLogger(__name__)
CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")
MIN_MARKET_CAP = Decimal("200000000000")
MIN_AVG_VOLUME = Decimal("10000000")


def new_message_push_market_cache() -> dict[str, dict[str, Any]]:
    return {
        market: {"cache_ready": False, "trade_date": None, "error": None, "bars": {}}
        for market in ("US", "HK")
    }


message_push_market_cache = new_message_push_market_cache()


class MessagePushCacheService:
    def __init__(
        self,
        longbridge: LongbridgeService,
        cache: dict[str, dict[str, Any]] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.longbridge = longbridge
        self.cache = cache if cache is not None else message_push_market_cache
        self._sleep = sleep
        self._locks = {market: asyncio.Lock() for market in ("US", "HK")}

    @staticmethod
    def china_date(china_now: datetime) -> date:
        if china_now.tzinfo is None:
            china_now = china_now.replace(tzinfo=CHINA_TIMEZONE)
        return china_now.astimezone(CHINA_TIMEZONE).date()

    def is_trading_day(self, market: str, china_now: datetime) -> bool:
        current_date = self.china_date(china_now)
        for attempt in range(1, 4):
            try:
                result = current_date in self.longbridge.get_trading_days(
                    market, current_date, current_date
                )
                logger.info(
                    "message_push_trading_day market=%s china_date=%s attempt=%s source=longbridge result=%s",
                    market,
                    current_date,
                    attempt,
                    result,
                )
                return result
            except Exception as exc:
                logger.warning(
                    "message_push_trading_day market=%s china_date=%s attempt=%s source=longbridge result=error error=%s",
                    market,
                    current_date,
                    attempt,
                    exc,
                )
                if attempt < 3:
                    self._sleep(attempt)
        fallback = current_date.weekday() < 5
        logger.warning(
            "message_push_trading_day market=%s china_date=%s source=weekday_fallback result=%s",
            market,
            current_date,
            fallback,
        )
        return fallback

    async def prepare_market(self, market: str, china_now: datetime) -> bool:
        current_date = self.china_date(china_now)
        async with self._locks[market]:
            state = self.cache[market]
            if state["cache_ready"] and state["trade_date"] == current_date:
                return True
            if state["trade_date"] != current_date:
                state.update(cache_ready=False, trade_date=None, error=None, bars={})

            last_error: Exception | None = None
            for attempt in range(1, 4):
                started = time.monotonic()
                try:
                    securities = self.longbridge.screen_securities(
                        market, MIN_MARKET_CAP, MIN_AVG_VOLUME
                    )
                    temporary = {
                        security.symbol: self.longbridge.get_daily_bars(
                            security.symbol, count=30
                        )
                        for security in securities
                    }
                    state.update(
                        cache_ready=True,
                        trade_date=current_date,
                        error=None,
                        bars=temporary,
                    )
                    logger.info(
                        "message_push_cache_init market=%s trade_date=%s attempt=%s screened=%s cached=%s elapsed=%.3f result=success",
                        market,
                        current_date,
                        attempt,
                        len(securities),
                        len(temporary),
                        time.monotonic() - started,
                    )
                    return True
                except Exception as exc:
                    last_error = exc
                    logger.warning(
                        "message_push_cache_init market=%s trade_date=%s attempt=%s elapsed=%.3f result=error error=%s",
                        market,
                        current_date,
                        attempt,
                        time.monotonic() - started,
                        exc,
                    )
                    if attempt < 3:
                        self._sleep(attempt)
            state.update(cache_ready=False, trade_date=current_date, error=str(last_error), bars={})
            return False

    async def screen_with_cached_bars(
        self, market: str, china_now: datetime
    ) -> tuple[list[Security], dict[str, list[MarketDataBar]]]:
        if not await self.prepare_market(market, china_now):
            return [], {}
        async with self._locks[market]:
            securities = self.longbridge.screen_securities(
                market, MIN_MARKET_CAP, MIN_AVG_VOLUME
            )
            state_bars = self.cache[market]["bars"]
            for security in securities:
                if security.symbol not in state_bars:
                    state_bars[security.symbol] = self.longbridge.get_daily_bars(
                        security.symbol, count=30
                    )
                    logger.info(
                        "message_push_cache_fill market=%s symbol=%s result=success",
                        market,
                        security.symbol,
                    )
            return securities, {
                security.symbol: state_bars[security.symbol]
                for security in securities
                if security.symbol in state_bars
            }
