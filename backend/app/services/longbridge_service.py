from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
import time
from typing import Any, Callable

from app.config import load_environment


SYMBOL_BATCH_SIZE = 50


@dataclass(frozen=True)
class IntradayBar:
    time: datetime
    close: float


@dataclass(frozen=True)
class MarketDataBar:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    turnover: Decimal | None


@dataclass(frozen=True)
class Security:
    symbol: str
    name: str
    market_cap: Decimal | None = None


@dataclass(frozen=True)
class SecurityStaticInfo:
    symbol: str
    name: str
    exchange: str | None
    currency: str | None
    lot_size: int | None


@dataclass(frozen=True)
class ScreenerIndicator:
    key: str
    name: str
    unit: str | None


@dataclass(frozen=True)
class LatestQuote:
    symbol: str
    price: float
    previous_close: float
    time: datetime
    session: str


class LongbridgeService:
    """Longbridge quote data adapter.

    If a quote context is injected, the service uses it directly. Otherwise it
    tries to build a real Longbridge SDK context from environment variables. If
    credentials or the SDK are unavailable, it falls back to deterministic data
    so local development and tests still run.
    """

    def __init__(
        self,
        quote_context: Any | None = None,
        screener_context: Any | None = None,
        sdk: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._sdk = sdk
        self._quote_context = quote_context
        self._screener_context = screener_context
        self._sleep = sleep
        self._retry_attempts = int(os.getenv("LONGBRIDGE_RETRY_ATTEMPTS", "4"))
        self._retry_delay_seconds = float(os.getenv("LONGBRIDGE_RETRY_DELAY_SECONDS", "1"))
        if self._quote_context is None or self._screener_context is None:
            quote_context, screener_context, sdk = self._create_context()
            self._quote_context = self._quote_context or quote_context
            self._screener_context = self._screener_context or screener_context
            self._sdk = self._sdk or sdk

    def get_daily_bars(self, symbol: str, count: int = 120) -> list[MarketDataBar]:
        if self._quote_context is None:
            return self._mock_market_bars(symbol, "1d", count)

        period = self._period("1d")
        candles = self._quote_context.candlesticks(
            symbol,
            period,
            count,
            self._sdk.AdjustType.NoAdjust,
        )
        return [self._market_bar_from_candle(candle) for candle in candles]

    def get_intraday_bars(self, symbol: str, interval: str = "5m", limit: int = 30) -> list[IntradayBar]:
        if self._quote_context is not None:
            period = self._period(interval)
            candles = self._quote_context.candlesticks(
                symbol,
                period,
                limit,
                self._sdk.AdjustType.NoAdjust,
            )
            return [
                IntradayBar(time=self._get_time(candle), close=float(getattr(candle, "close")))
                for candle in candles
            ]

        return [
            IntradayBar(time=bar.time, close=bar.close)
            for bar in self._mock_market_bars(symbol, interval, limit)
        ]

    def list_securities(self, market: str) -> list[Security]:
        if self._quote_context is None:
            return [Security(symbol="AAPL.US" if market == "US" else "700.HK", name="Apple" if market == "US" else "腾讯控股")]

        securities = self._quote_context.security_list(self._market(market))
        return [
            Security(
                symbol=getattr(item, "symbol"),
                name=_first_text(item, "name_cn", "name_hk", "name_en", default=getattr(item, "symbol")),
            )
            for item in securities
        ]

    def get_static_info(self, symbols: list[str]) -> list[SecurityStaticInfo]:
        if self._quote_context is None:
            return [
                SecurityStaticInfo(
                    symbol=symbol,
                    name="Apple" if symbol.endswith(".US") else "腾讯控股",
                    exchange="NASDAQ" if symbol.endswith(".US") else "HKEX",
                    currency="USD" if symbol.endswith(".US") else "HKD",
                    lot_size=1 if symbol.endswith(".US") else 100,
                )
                for symbol in symbols
            ]

        static_infos: list[SecurityStaticInfo] = []
        for symbol_batch in _chunks(symbols, SYMBOL_BATCH_SIZE):
            infos = self._call_with_retries(lambda: self._quote_context.static_info(symbol_batch))
            static_infos.extend(
                SecurityStaticInfo(
                    symbol=getattr(item, "symbol"),
                    name=_first_text(item, "name_cn", "name_hk", "name_en", default=getattr(item, "symbol")),
                    exchange=getattr(item, "exchange", None),
                    currency=getattr(item, "currency", None),
                    lot_size=getattr(item, "lot_size", None),
                )
                for item in infos
            )
        return static_infos

    def get_market_caps(self, symbols: list[str]) -> dict[str, Decimal]:
        if self._quote_context is None:
            return {
                symbol: Decimal("3200000000000") if symbol.endswith(".US") else Decimal("3600000000000")
                for symbol in symbols
            }

        market_caps: dict[str, Decimal] = {}
        for symbol_batch in _chunks(symbols, SYMBOL_BATCH_SIZE):
            indexes = self._call_with_retries(
                lambda: self._quote_context.calc_indexes(symbol_batch, [self._sdk.CalcIndex.TotalMarketValue])
            )
            market_caps.update(
                {
                    getattr(item, "symbol"): Decimal(str(getattr(item, "total_market_value")))
                    for item in indexes
                    if getattr(item, "total_market_value", None) is not None
                }
            )
        return market_caps

    def get_latest_quotes(self, symbols: list[str]) -> dict[str, LatestQuote]:
        if self._quote_context is None:
            return self._mock_latest_quotes(symbols)

        latest_quotes: dict[str, LatestQuote] = {}
        for symbol_batch in _chunks(symbols, SYMBOL_BATCH_SIZE):
            quotes = self._call_with_retries(lambda: self._quote_context.quote(symbol_batch))
            for item in quotes:
                latest_quote = _latest_quote_from_quote_item(item)
                if latest_quote is not None:
                    latest_quotes[latest_quote.symbol] = latest_quote
        return latest_quotes

    def screen_securities(
        self,
        market: str,
        min_market_cap: Decimal,
        min_avg_volume: Decimal,
        page_size: int = 100,
    ) -> list[Security]:
        if self._screener_context is None:
            return self._mock_screen_securities(market)

        indicators = self._screener_indicators()
        marketcap = _find_indicator(indicators, ["marketcap"], ["市值", "market cap"])
        volume = _find_indicator(
            indicators,
            ["onemonthamount", "avgvolume", "averagevolume", "total_amount", "volume"],
            ["月平均成交量", "月均成交量", "1 month volume", "one month volume", "average volume", "avg volume", "成交量", "volume"],
        )
        conditions = [
            self._sdk.ScreenerCondition(
                marketcap.key,
                _condition_value(min_market_cap, marketcap.unit),
                "",
            ),
            self._sdk.ScreenerCondition(
                volume.key,
                _condition_value(min_avg_volume, volume.unit),
                "",
            ),
        ]

        securities: list[Security] = []
        page = 0
        while True:
            response = self._call_with_retries(
                lambda: self._screener_context.screener_search(
                    market,
                    None,
                    conditions,
                    [marketcap.key, volume.key],
                    page,
                    page_size,
                )
            )
            items = _items_from_screener_response(response)
            if not items:
                break
            securities.extend(_security_from_screener_item(item) for item in items)
            if len(items) < page_size:
                break
            page += 1
        return securities

    def _screener_indicators(self) -> list[ScreenerIndicator]:
        response = self._screener_context.screener_indicators()
        indicators: list[ScreenerIndicator] = []
        for group in response.data.get("groups", []):
            for item in group.get("indicators", []):
                indicators.append(
                    ScreenerIndicator(
                        key=str(item.get("key")),
                        name=str(item.get("name", "")),
                        unit=item.get("unit"),
                    )
                )
        return indicators

    def _call_with_retries(self, operation: Callable[[], Any]) -> Any:
        for attempt in range(self._retry_attempts):
            try:
                return operation()
            except Exception as exc:
                if not _is_rate_limit_error(exc) or attempt >= self._retry_attempts - 1:
                    raise
                self._sleep(self._retry_delay_seconds * (attempt + 1))
        raise RuntimeError("unreachable retry state")

    def _create_context(self) -> tuple[Any | None, Any | None, Any | None]:
        load_environment()
        if not all(
            os.getenv(name)
            for name in (
                "LONGBRIDGE_APP_KEY",
                "LONGBRIDGE_APP_SECRET",
                "LONGBRIDGE_ACCESS_TOKEN",
            )
        ):
            return None, None, None
        try:
            from longbridge import openapi as sdk

            config = sdk.Config.from_apikey_env()
            return sdk.QuoteContext(config), sdk.ScreenerContext(config), sdk
        except Exception:
            return None, None, None

    def _period(self, interval: str) -> Any:
        mapping = {
            "1d": "Day",
            "day": "Day",
            "1m": "Min_1",
            "2m": "Min_2",
            "3m": "Min_3",
            "5m": "Min_5",
            "10m": "Min_10",
            "15m": "Min_15",
            "30m": "Min_30",
            "60m": "Min_60",
        }
        period_name = mapping.get(interval)
        if period_name is None:
            raise ValueError(f"unsupported Longbridge candlestick interval: {interval}")
        return getattr(self._sdk.Period, period_name)

    def _market(self, market: str) -> Any:
        if market not in {"US", "HK"}:
            raise ValueError(f"unsupported Longbridge market: {market}")
        return getattr(self._sdk.Market, market)

    def _market_bar_from_candle(self, candle: Any) -> MarketDataBar:
        return MarketDataBar(
            time=self._get_time(candle),
            open=float(getattr(candle, "open")),
            high=float(getattr(candle, "high")),
            low=float(getattr(candle, "low")),
            close=float(getattr(candle, "close")),
            volume=int(getattr(candle, "volume")),
            turnover=_decimal_or_none(getattr(candle, "turnover", None)),
        )

    def _get_time(self, candle: Any) -> datetime:
        raw_time = getattr(candle, "timestamp", None) or getattr(candle, "time", None)
        if isinstance(raw_time, datetime):
            return raw_time
        raise ValueError("Longbridge candlestick is missing timestamp")

    def _mock_market_bars(self, symbol: str, interval: str, count: int) -> list[MarketDataBar]:
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        base = 100.0
        if symbol.endswith(".US"):
            base = 200.0
        if symbol.endswith(".HK"):
            base = 360.0

        minutes = 1440 if interval in {"1d", "day"} else 5
        bars: list[MarketDataBar] = []
        for index in range(count):
            close = base + index * 0.2
            if interval not in {"1d", "day"} and index == count - 1:
                close = base + 8.0
            bars.append(
                MarketDataBar(
                    time=now - timedelta(minutes=(count - index) * minutes),
                    open=close - 0.5,
                    high=close + 1.0,
                    low=close - 1.0,
                    close=close,
                    volume=10_000_000 + index * 1000,
                    turnover=Decimal(str(close * (10_000_000 + index * 1000))),
                )
            )
        return bars

    def _mock_screen_securities(self, market: str) -> list[Security]:
        return [
            Security(
                symbol="AAPL.US" if market == "US" else "700.HK",
                name="Apple" if market == "US" else "腾讯控股",
                market_cap=Decimal("3200000000000") if market == "US" else Decimal("3600000000000"),
            )
        ]

    def _mock_latest_quotes(self, symbols: list[str]) -> dict[str, LatestQuote]:
        latest_quotes: dict[str, LatestQuote] = {}
        for symbol in symbols:
            bar = self._mock_market_bars(symbol, "5m", 30)[-1]
            latest_quotes[symbol] = LatestQuote(
                symbol=symbol,
                price=bar.close,
                previous_close=bar.close - 10,
                time=bar.time,
                session="regular",
            )
        return latest_quotes


def _first_text(item: Any, *names: str, default: str) -> str:
    for name in names:
        value = getattr(item, name, None)
        if value:
            return str(value)
    return default


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _quote_time_or_none(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _quote_candidate(item: Any, symbol: str, session: str) -> LatestQuote | None:
    price = _float_or_none(getattr(item, "last_done", None))
    previous_close = _float_or_none(getattr(item, "prev_close", None))
    quote_time = _quote_time_or_none(getattr(item, "timestamp", None))
    if price is None or previous_close is None or quote_time is None:
        return None
    return LatestQuote(symbol=symbol, price=price, previous_close=previous_close, time=quote_time, session=session)


def _latest_quote_from_quote_item(item: Any) -> LatestQuote | None:
    symbol = str(getattr(item, "symbol"))
    candidates = [
        _quote_candidate(item, symbol, "regular"),
        _quote_candidate(getattr(item, "pre_market_quote", None), symbol, "pre_market"),
        _quote_candidate(getattr(item, "post_market_quote", None), symbol, "post_market"),
        _quote_candidate(getattr(item, "overnight_quote", None), symbol, "overnight"),
    ]
    valid_candidates = [candidate for candidate in candidates if candidate is not None]
    if not valid_candidates:
        return None
    return max(valid_candidates, key=lambda quote: quote.time)


def _is_rate_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "429002" in message or "request is limited" in message or "slow down request frequency" in message


def _find_indicator(indicators: list[ScreenerIndicator], key_candidates: list[str], name_candidates: list[str]) -> ScreenerIndicator:
    for candidate in key_candidates:
        normalized_key = candidate.lower()
        for indicator in indicators:
            if indicator.key.lower() == normalized_key:
                return indicator
    for candidate in name_candidates:
        normalized_name = candidate.lower()
        for indicator in indicators:
            if normalized_name in indicator.name.lower():
                return indicator
    raise ValueError(f"missing Longbridge screener indicator: {', '.join(name_candidates)}")


def _condition_value(value: Decimal, unit: str | None) -> str:
    text = format(value / _unit_divisor(unit), "f")
    if "." in text:
        return text.rstrip("0").rstrip(".")
    return text


def _unit_divisor(unit: str | None) -> Decimal:
    normalized = (unit or "").strip().lower()
    if not normalized:
        return Decimal("1")
    if "万" in normalized:
        return Decimal("10000")
    if "亿" in normalized or "100m" in normalized:
        return Decimal("100000000")
    if normalized in {"k", "thousand"} or "千" in normalized:
        return Decimal("1000")
    if normalized in {"m", "mn", "million"} or "百万" in normalized:
        return Decimal("1000000")
    if normalized in {"b", "bn", "billion"} or "十亿" in normalized:
        return Decimal("1000000000")
    return Decimal("1")


def _items_from_screener_response(response: Any) -> list[Any]:
    data = response.data
    if isinstance(data, dict):
        items = data.get("items") or data.get("list") or data.get("lists") or data.get("securities") or []
        return list(items)
    return []


def _security_from_screener_item(item: Any) -> Security:
    if isinstance(item, dict):
        symbol = _screener_symbol(item)
        name = str(item.get("name") or item.get("name_cn") or item.get("name_en") or symbol)
        return Security(symbol=symbol, name=name, market_cap=_decimal_or_none(_screener_value(item, "marketcap")))
    symbol = str(getattr(item, "symbol"))
    return Security(
        symbol=symbol,
        name=_first_text(item, "name_cn", "name_hk", "name_en", "name", default=symbol),
        market_cap=_decimal_or_none(getattr(item, "marketcap", None)),
    )


def _screener_symbol(item: dict[str, Any]) -> str:
    symbol = item.get("symbol") or item.get("security_code") or item.get("code")
    if symbol:
        return str(symbol)

    counter_id = item.get("counter_id")
    if isinstance(counter_id, str):
        parts = counter_id.split("/")
        if len(parts) == 3 and parts[0] == "ST":
            market = parts[1]
            code = parts[2].lstrip("0") or parts[2]
            if market in {"US", "HK"}:
                return f"{code}.{market}"
    return str(counter_id)


def _screener_value(item: dict[str, Any], key: str) -> Any:
    if key in item:
        return item[key]
    for indicator in item.get("indicators", []):
        if indicator.get("key") == key:
            return indicator.get("value") or indicator.get("value_raw")
    return None
