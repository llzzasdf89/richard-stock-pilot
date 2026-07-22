from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any


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


@dataclass(frozen=True)
class SecurityStaticInfo:
    symbol: str
    name: str
    exchange: str | None
    currency: str | None
    lot_size: int | None


class LongbridgeService:
    """Longbridge quote data adapter.

    If a quote context is injected, the service uses it directly. Otherwise it
    tries to build a real Longbridge SDK context from environment variables. If
    credentials or the SDK are unavailable, it falls back to deterministic data
    so local development and tests still run.
    """

    def __init__(self, quote_context: Any | None = None, sdk: Any | None = None) -> None:
        self._sdk = sdk
        self._quote_context = quote_context
        if self._quote_context is None:
            self._quote_context, self._sdk = self._create_context()

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

        infos = self._quote_context.static_info(symbols)
        return [
            SecurityStaticInfo(
                symbol=getattr(item, "symbol"),
                name=_first_text(item, "name_cn", "name_hk", "name_en", default=getattr(item, "symbol")),
                exchange=getattr(item, "exchange", None),
                currency=getattr(item, "currency", None),
                lot_size=getattr(item, "lot_size", None),
            )
            for item in infos
        ]

    def get_market_caps(self, symbols: list[str]) -> dict[str, Decimal]:
        if self._quote_context is None:
            return {
                symbol: Decimal("3200000000000") if symbol.endswith(".US") else Decimal("3600000000000")
                for symbol in symbols
            }

        indexes = self._quote_context.calc_indexes(symbols, [self._sdk.CalcIndex.TotalMarketValue])
        return {
            getattr(item, "symbol"): Decimal(str(getattr(item, "total_market_value")))
            for item in indexes
            if getattr(item, "total_market_value", None) is not None
        }

    def _create_context(self) -> tuple[Any | None, Any | None]:
        try:
            from longbridge import openapi as sdk

            config = sdk.Config.from_apikey_env()
            return sdk.QuoteContext(config), sdk
        except Exception:
            return None, None

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


def _first_text(item: Any, *names: str, default: str) -> str:
    for name in names:
        value = getattr(item, name, None)
        if value:
            return str(value)
    return default


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))
