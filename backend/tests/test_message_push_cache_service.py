from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal

from app.services.longbridge_service import MarketDataBar, Security
from app.services.message_push_cache_service import (
    MessagePushCacheService,
    new_message_push_market_cache,
)


def bar(day: int) -> MarketDataBar:
    return MarketDataBar(
        time=datetime(2026, 7, day, tzinfo=timezone.utc),
        open=100,
        high=101,
        low=99,
        close=100,
        volume=20_000_000,
        turnover=Decimal("2000000000"),
    )


class FakeLongbridge:
    def __init__(self):
        self.trading_outcomes = []
        self.screens = {
            "US": [Security("AAPL.US", "Apple", Decimal("3000000000000"))],
            "HK": [Security("700.HK", "腾讯", Decimal("3000000000000"))],
        }
        self.daily_calls = []
        self.screen_calls = []

    def get_trading_days(self, market, start, end):
        outcome = self.trading_outcomes.pop(0) if self.trading_outcomes else {start}
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def screen_securities(self, market, min_market_cap, min_avg_volume):
        self.screen_calls.append((market, min_market_cap, min_avg_volume))
        return self.screens[market]

    def get_daily_bars(self, symbol, count=30):
        self.daily_calls.append((symbol, count))
        return [bar(day) for day in range(1, 31)]


def test_trading_day_retries_three_times_then_uses_china_weekday():
    provider = FakeLongbridge()
    provider.trading_outcomes = [RuntimeError("x"), RuntimeError("y"), RuntimeError("z")]
    service = MessagePushCacheService(provider, cache=new_message_push_market_cache(), sleep=lambda _: None)
    china_now = datetime(2026, 7, 30, 10, tzinfo=timezone.utc)

    assert service.is_trading_day("US", china_now) is True
    assert provider.trading_outcomes == []


def test_normal_holiday_response_does_not_fall_back_to_weekday():
    provider = FakeLongbridge()
    provider.trading_outcomes = [set()]
    service = MessagePushCacheService(provider, cache=new_message_push_market_cache(), sleep=lambda _: None)

    assert service.is_trading_day("US", datetime(2026, 7, 30, 10, tzinfo=timezone.utc)) is False


def test_market_cache_preloads_and_only_fetches_later_missing_symbol():
    provider = FakeLongbridge()
    cache = new_message_push_market_cache()
    service = MessagePushCacheService(provider, cache=cache, sleep=lambda _: None)
    now = datetime(2026, 7, 30, 10, tzinfo=timezone.utc)

    assert asyncio.run(service.prepare_market("US", now)) is True
    assert cache["US"]["cache_ready"] is True
    assert cache["US"]["trade_date"] == date(2026, 7, 30)
    assert list(cache["US"]["bars"]) == ["AAPL.US"]
    asyncio.run(service.prepare_market("US", now))
    assert provider.daily_calls == [("AAPL.US", 30)]

    provider.screens["US"].append(Security("MSFT.US", "Microsoft", Decimal("3000000000000")))
    securities, bars = asyncio.run(service.screen_with_cached_bars("US", now))
    assert [item.symbol for item in securities] == ["AAPL.US", "MSFT.US"]
    assert set(bars) == {"AAPL.US", "MSFT.US"}
    assert provider.daily_calls[-1] == ("MSFT.US", 30)


def test_failed_market_does_not_publish_partial_cache():
    provider = FakeLongbridge()
    provider.screens["US"].append(Security("FAIL.US", "Fail", Decimal("3000000000000")))
    original = provider.get_daily_bars

    def failing_bars(symbol, count=30):
        if symbol == "FAIL.US":
            raise RuntimeError("boom")
        return original(symbol, count)

    provider.get_daily_bars = failing_bars
    cache = new_message_push_market_cache()
    service = MessagePushCacheService(provider, cache=cache, sleep=lambda _: None)

    assert asyncio.run(service.prepare_market("US", datetime(2026, 7, 30, 10, tzinfo=timezone.utc))) is False
    assert cache["US"]["cache_ready"] is False
    assert cache["US"]["bars"] == {}
    assert "boom" in cache["US"]["error"]
