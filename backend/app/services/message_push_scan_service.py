from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import html
import logging
from typing import Any
from zoneinfo import ZoneInfo

from app.services.indicator_service import DailyPriceBar, HistoricalSetup, calculate_historical_setup
from app.services.longbridge_service import LongbridgeService
from app.services.message_push_cache_service import MessagePushCacheService
from app.services.pushplus_message_service import PushPlusMessageService


logger = logging.getLogger(__name__)
CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class ScanSummary:
    market: str
    screened: int
    matched: int
    sent: int
    failed: int


def derive_entry_direction(setup: HistoricalSetup) -> str | None:
    if setup.is_suitable_for_entry != "是" or setup.has_reversal_trend != "否":
        return None
    if (
        setup.ma20_direction == "上升"
        and setup.z_score is not None
        and setup.z_score <= -1.5
    ):
        return "做多"
    if (
        setup.ma20_direction == "下降"
        and setup.z_score is not None
        and setup.z_score >= 1.5
    ):
        return "做空"
    return None


def build_pushplus_message(
    opportunity: dict[str, Any], scan_time: datetime
) -> tuple[str, str]:
    market_name = "美股" if opportunity["market"] == "US" else "港股"
    title = (
        f"{market_name}｜{opportunity['symbol']} {opportunity['name']}｜"
        f"{opportunity['direction']}｜现价 {opportunity['price']:.2f}"
    )
    china_time = scan_time.astimezone(CHINA_TIMEZONE)
    rows = [
        ("提醒类型", "建仓机会提醒"),
        ("市场", market_name),
        ("股票", f"{opportunity['symbol']} / {opportunity['name']}"),
        ("建仓方向", opportunity["direction"]),
        ("当前价格", f"{opportunity['price']:.2f} {opportunity['currency']}"),
        ("布林上轨", f"{opportunity['boll_upper']:.2f}"),
        ("布林中轨", f"{opportunity['boll_mid']:.2f}"),
        ("布林下轨", f"{opportunity['boll_lower']:.2f}"),
        ("MA20方向", opportunity["ma20_direction"]),
        ("Z-Score", f"{opportunity['z_score']:.2f}"),
        ("ATR14", f"{opportunity['atr14']:.2f}"),
        ("扫描时间", china_time.strftime("%Y-%m-%d %H:%M:%S")),
    ]
    content = "<br>".join(
        f"{html.escape(str(label))}：{html.escape(str(value))}" for label, value in rows
    )
    return title, content


class MessagePushScanService:
    def __init__(
        self,
        cache_service: MessagePushCacheService,
        longbridge: LongbridgeService,
        sender: PushPlusMessageService,
    ) -> None:
        self.cache_service = cache_service
        self.longbridge = longbridge
        self.sender = sender

    async def run_once(self, china_now: datetime | None = None) -> list[ScanSummary]:
        now = china_now or datetime.now(timezone.utc)
        summaries: list[ScanSummary] = []
        for market in ("US", "HK"):
            try:
                if not self.cache_service.is_trading_day(market, now):
                    continue
                summaries.append(await self.scan_market(market, now))
            except Exception:
                logger.exception("message_push_scan market=%s result=error", market)
        return summaries

    async def scan_market(self, market: str, china_now: datetime) -> ScanSummary:
        securities, bars_by_symbol = await self.cache_service.screen_with_cached_bars(
            market, china_now
        )
        symbols = [security.symbol for security in securities]
        quotes = self.longbridge.get_latest_quotes(symbols) if symbols else {}
        matched = sent = failed = 0
        for security in securities:
            try:
                quote = quotes.get(security.symbol)
                bars = bars_by_symbol.get(security.symbol, [])
                if quote is None:
                    continue
                evaluation_date = _market_date(china_now, market)
                historical = [
                    DailyPriceBar(
                        trade_date=_market_date(bar.time, market),
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                    )
                    for bar in bars
                    if _market_date(bar.time, market) < evaluation_date
                ]
                setup = calculate_historical_setup(historical, current_price=quote.price)
                direction = derive_entry_direction(setup)
                if direction is None:
                    continue
                matched += 1
                if None in (
                    setup.boll_upper,
                    setup.boll_mid,
                    setup.boll_lower,
                    setup.z_score,
                ):
                    continue
                opportunity = {
                    "market": market,
                    "symbol": security.symbol,
                    "name": security.name,
                    "direction": direction,
                    "price": quote.price,
                    "currency": "USD" if market == "US" else "HKD",
                    "boll_upper": setup.boll_upper,
                    "boll_mid": setup.boll_mid,
                    "boll_lower": setup.boll_lower,
                    "ma20_direction": setup.ma20_direction,
                    "z_score": setup.z_score,
                    "atr14": setup.atr14,
                }
                title, content = build_pushplus_message(opportunity, china_now)
                self.sender.send_message(title, content)
                sent += 1
                logger.info(
                    "message_push_stock market=%s symbol=%s direction=%s result=success",
                    market,
                    security.symbol,
                    direction,
                )
            except Exception:
                failed += 1
                logger.exception(
                    "message_push_stock market=%s symbol=%s result=error",
                    market,
                    security.symbol,
                )
        summary = ScanSummary(market, len(securities), matched, sent, failed)
        logger.info(
            "message_push_scan market=%s screened=%s matched=%s sent=%s failed=%s",
            market,
            summary.screened,
            summary.matched,
            summary.sent,
            summary.failed,
        )
        return summary


def _market_date(value: datetime, market: str):
    timezone_name = "America/New_York" if market == "US" else "Asia/Hong_Kong"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo(timezone_name)).date()
