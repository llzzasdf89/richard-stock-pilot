from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.services.indicator_service import HistoricalSetup
from app.services.longbridge_service import LatestQuote, MarketDataBar, Security
from app.services.message_push_scan_service import (
    MessagePushScanService,
    build_pushplus_message,
    derive_entry_direction,
)


def setup(direction: str, z_score: float, suitable: str = "是") -> HistoricalSetup:
    return HistoricalSetup(
        ma20_direction=direction,
        z_score=z_score,
        atr14=2,
        previous_10d_low=80,
        previous_10d_high=120,
        boll_mid=100,
        boll_upper=110,
        boll_lower=90,
        has_reversal_trend="否",
        is_suitable_for_entry=suitable,
    )


def test_direction_is_derived_without_changing_suitability():
    assert derive_entry_direction(setup("上升", -1.5)) == "做多"
    assert derive_entry_direction(setup("下降", 1.5)) == "做空"
    assert derive_entry_direction(setup("上升", -1.5, suitable="否")) is None
    assert derive_entry_direction(setup("上升", -1.49)) is None


def test_message_has_required_fields_and_no_detail_link():
    title, content = build_pushplus_message(
        {
            "market": "US",
            "symbol": "AAPL.US",
            "name": "Apple",
            "direction": "做多",
            "price": 89,
            "currency": "USD",
            "boll_upper": 110,
            "boll_mid": 100,
            "boll_lower": 90,
            "ma20_direction": "上升",
            "z_score": -1.75,
            "atr14": 2,
        },
        datetime(2026, 7, 30, 15, tzinfo=timezone.utc),
    )
    assert title == "美股｜AAPL.US Apple｜做多｜现价 89.00"
    assert "布林下轨：90.00" in content
    assert "Z-Score：-1.75" in content
    assert "突破幅度" not in content
    assert "详情" not in content
    assert "http" not in content


class FakeCache:
    def is_trading_day(self, market, now):
        return True

    async def screen_with_cached_bars(self, market, now):
        symbol = "AAPL.US" if market == "US" else "700.HK"
        security = Security(symbol, "Apple" if market == "US" else "腾讯", Decimal("3000000000000"))
        start = datetime(2026, 7, 1, tzinfo=timezone.utc)
        bars = []
        for index in range(25):
            close = 90 if index < 5 else 95 + index
            low = 50 if index == 20 else close - 1
            bars.append(
                MarketDataBar(
                    time=start + timedelta(days=index),
                    open=close,
                    high=close + 1,
                    low=low,
                    close=close,
                    volume=20_000_000,
                    turnover=Decimal("2000000000"),
                )
            )
        return [security], {symbol: bars}


class FakeLongbridge:
    def get_latest_quotes(self, symbols):
        return {
            symbol: LatestQuote(
                symbol=symbol,
                price=100,
                previous_close=101,
                time=datetime(2026, 7, 30, 1, tzinfo=timezone.utc),
                session="overnight",
            )
            for symbol in symbols
        }


class FakeSender:
    def __init__(self):
        self.messages = []

    def send_message(self, title, content):
        self.messages.append((title, content))
        return {"code": 200}


def test_run_once_sends_one_message_per_matching_stock_for_both_markets():
    sender = FakeSender()
    service = MessagePushScanService(FakeCache(), FakeLongbridge(), sender)

    summaries = asyncio.run(
        service.run_once(datetime(2026, 7, 30, 9, tzinfo=timezone.utc))
    )

    assert [summary.market for summary in summaries] == ["US", "HK"]
    assert [summary.sent for summary in summaries] == [1, 1]
    assert len(sender.messages) == 2
