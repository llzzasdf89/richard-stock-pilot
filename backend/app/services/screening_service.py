from __future__ import annotations

from decimal import Decimal
from math import ceil
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.stock import Stock
from app.models.stock_metric import StockMetricDaily
from app.services.indicator_service import (
    DailyPriceBar,
    calculate_bollinger,
    calculate_break_percent,
    calculate_historical_setup,
    detect_boll_signal,
)
from app.services.longbridge_service import LongbridgeService


def _to_float(value: Decimal | int | float | None) -> float | None:
    return float(value) if value is not None else None


def _metric_row(stock: Stock, metric: StockMetricDaily) -> dict[str, Any]:
    close = _to_float(metric.close)
    return {
        "symbol": stock.symbol,
        "name": stock.name,
        "market": stock.market,
        "currency": stock.currency,
        "signal_type": metric.signal_type,
        "earnings_date": stock.earnings_date.isoformat() if stock.earnings_date is not None else None,
        "trade_date": metric.trade_date.isoformat(),
        "close": close,
        "latest_price": close,
        "market_cap": _to_float(metric.market_cap),
        "avg_volume_1m": _to_float(metric.avg_volume_1m),
        "boll_upper": _to_float(metric.boll_upper),
        "boll_mid": _to_float(metric.boll_mid),
        "boll_lower": _to_float(metric.boll_lower),
        "break_percent": _to_float(metric.break_percent),
        "ma20_direction": metric.ma20_direction,
        "atr14": _to_float(metric.atr14),
        "previous_10d_low": _to_float(metric.previous_10d_low),
        "previous_10d_high": _to_float(metric.previous_10d_high),
        "has_reversal_trend": metric.has_reversal_trend,
        "is_suitable_for_entry": metric.is_suitable_for_entry,
        "data_time": metric.trade_date.isoformat(),
    }


def _apply_filters(
    statement: Select[tuple[Stock, StockMetricDaily]],
    market: str,
    signal_type: str,
    min_market_cap: Decimal,
    min_avg_volume: Decimal,
) -> Select[tuple[Stock, StockMetricDaily]]:
    statement = statement.where(
        StockMetricDaily.market_cap >= min_market_cap,
        StockMetricDaily.avg_volume_1m >= min_avg_volume,
        StockMetricDaily.signal_type != "none",
    )
    if market != "all":
        statement = statement.where(Stock.market == market)
    if signal_type != "all":
        statement = statement.where(StockMetricDaily.signal_type == signal_type)
    return statement


def _latest_metric_dates_by_market(session: Session, market: str) -> list[tuple[str, Any]]:
    statement = (
        select(Stock.market, func.max(StockMetricDaily.trade_date))
        .join(StockMetricDaily, StockMetricDaily.stock_id == Stock.id)
        .group_by(Stock.market)
    )
    if market != "all":
        statement = statement.where(Stock.market == market)
    return [(row[0], row[1]) for row in session.execute(statement).all() if row[1] is not None]


def _latest_metric_base_statement(session: Session, market: str) -> tuple[Select[tuple[Stock, StockMetricDaily]] | None, Any | None]:
    latest_dates = _latest_metric_dates_by_market(session, market)
    if not latest_dates:
        return None, None

    latest_conditions = [
        and_(Stock.market == market_name, StockMetricDaily.trade_date == trade_date)
        for market_name, trade_date in latest_dates
    ]
    latest_date = max(trade_date for _, trade_date in latest_dates)
    return (
        select(Stock, StockMetricDaily)
        .join(StockMetricDaily, StockMetricDaily.stock_id == Stock.id)
        .where(or_(*latest_conditions)),
        latest_date,
    )


def _markets(market: str) -> list[str]:
    if market == "all":
        return ["US", "HK"]
    return [market]


def _symbol_market(symbol: str) -> str:
    if symbol.endswith(".US"):
        return "US"
    if symbol.endswith(".HK"):
        return "HK"
    raise ValueError(f"unsupported security symbol market: {symbol}")


def _market_date(value: Any, market: str) -> Any:
    timezone_name = "America/New_York" if market == "US" else "Asia/Hong_Kong"
    if value.tzinfo is None:
        return value.date()
    return value.astimezone(ZoneInfo(timezone_name)).date()


def _get_earnings_dates(provider: LongbridgeService, symbols: list[str], market: str) -> dict[str, Any]:
    get_dates = getattr(provider, "get_earnings_dates", None)
    if get_dates is None:
        return {}
    if market != "all":
        return get_dates(symbols, market=market)

    earnings_dates: dict[str, Any] = {}
    for market_name in _markets(market):
        market_symbols = [symbol for symbol in symbols if _symbol_market(symbol) == market_name]
        if market_symbols:
            earnings_dates.update(get_dates(market_symbols, market=market_name))
    return earnings_dates


def get_daily_screenings(
    session: Session,
    market: str,
    signal_type: str,
    min_market_cap: Decimal,
    min_avg_volume: Decimal,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    if page < 1 or page_size < 1:
        raise ValueError("page and page_size must be positive")

    base, latest_date = _latest_metric_base_statement(session, market)
    if base is None or latest_date is None:
        return {"data_date": None, "page": page, "page_size": page_size, "total": 0, "results": []}

    filtered = _apply_filters(base, market, signal_type, min_market_cap, min_avg_volume)
    count_statement = select(func.count()).select_from(filtered.subquery())
    total = session.scalar(count_statement) or 0
    rows = session.execute(
        filtered.order_by(StockMetricDaily.break_percent.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return {
        "data_date": latest_date.isoformat(),
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": ceil(total / page_size) if total else 0,
        "results": [_metric_row(stock, metric) for stock, metric in rows],
    }


def get_intraday_screenings(
    session: Session,
    market: str,
    signal_type: str,
    min_market_cap: Decimal,
    min_avg_volume: Decimal,
    interval: str,
    page: int,
    page_size: int,
    longbridge: LongbridgeService | None = None,
) -> dict[str, Any]:
    if page < 1 or page_size < 1:
        raise ValueError("page and page_size must be positive")

    provider = longbridge or LongbridgeService()
    securities = [
        security
        for market_name in _markets(market)
        for security in provider.screen_securities(
            market=market_name,
            min_market_cap=min_market_cap,
            min_avg_volume=min_avg_volume,
        )
    ]
    symbols = [security.symbol for security in securities]
    if not symbols:
        return {
            "refreshed_at": None,
            "interval": interval,
            "page": page,
            "page_size": page_size,
            "total": 0,
            "total_pages": 0,
            "results": [],
        }
    latest_quotes = provider.get_latest_quotes(symbols)
    earnings_dates = _get_earnings_dates(provider, symbols, market)
    results: list[dict[str, Any]] = []
    refreshed_at: str | None = None
    for security in securities:
        daily_bars = provider.get_daily_bars(security.symbol, count=30)
        if len(daily_bars) < 20:
            continue
        avg_volume = sum(bar.volume for bar in daily_bars[-20:]) / min(20, len(daily_bars))
        if Decimal(str(avg_volume)) < min_avg_volume:
            continue

        bars = provider.get_intraday_bars(security.symbol, interval=interval, limit=30)
        if len(bars) < 21:
            continue
        latest_quote = latest_quotes.get(security.symbol)
        previous_close = latest_quote.previous_close if latest_quote is not None else daily_bars[-1].close
        latest_price = latest_quote.price if latest_quote is not None else bars[-1].close
        latest_time = latest_quote.time if latest_quote is not None else bars[-1].time
        refreshed_at = latest_time.isoformat()
        row_market = "US" if security.symbol.endswith(".US") else "HK"
        evaluation_date = _market_date(latest_time, row_market)
        historical_daily_bars = [
            bar
            for bar in daily_bars
            if _market_date(bar.time, row_market) < evaluation_date
        ]
        setup = calculate_historical_setup(
            [
                DailyPriceBar(
                    trade_date=_market_date(bar.time, row_market),
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                )
                for bar in historical_daily_bars
            ],
            current_price=latest_price,
        )
        historical_closes = [bar.close for bar in historical_daily_bars]
        historical_bands = calculate_bollinger(historical_closes, period=20, std_multiplier=2)
        current = historical_bands[-1] if historical_bands else {"mid": None, "upper": None, "lower": None}
        if None in (current["mid"], current["upper"], current["lower"]):
            continue
        current_signal = detect_boll_signal(
            prev_close=previous_close,
            close=latest_price,
            prev_upper=float(current["upper"]),
            upper=float(current["upper"]),
            prev_lower=float(current["lower"]),
            lower=float(current["lower"]),
        )
        if current_signal == "none" or (signal_type != "all" and signal_type != current_signal):
            continue
        results.append(
            {
                "symbol": security.symbol,
                "name": security.name,
                "market": row_market,
                "currency": "USD" if security.symbol.endswith(".US") else "HKD",
                "signal_type": current_signal,
                "earnings_date": earnings_dates.get(security.symbol).isoformat()
                if earnings_dates.get(security.symbol) is not None
                else None,
                "interval": interval,
                "latest_bar_time": bars[-1].time.isoformat(),
                "close": previous_close,
                "latest_price": latest_price,
                "market_cap": _to_float(security.market_cap),
                "avg_volume_1m": avg_volume,
                "boll_upper": current["upper"],
                "boll_mid": current["mid"],
                "boll_lower": current["lower"],
                "break_percent": calculate_break_percent(
                    current_signal,
                    close=latest_price,
                    upper=float(current["upper"]),
                    lower=float(current["lower"]),
                ),
                "ma20_direction": setup.ma20_direction,
                "atr14": setup.atr14,
                "previous_10d_low": setup.previous_10d_low,
                "previous_10d_high": setup.previous_10d_high,
                "has_reversal_trend": setup.has_reversal_trend,
                "is_suitable_for_entry": setup.is_suitable_for_entry,
                "data_time": latest_time.isoformat(),
            }
        )

    total = len(results)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "refreshed_at": refreshed_at,
        "interval": interval,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": ceil(total / page_size) if total else 0,
        "results": results[start:end],
    }
