from __future__ import annotations

from decimal import Decimal
from math import ceil
from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.stock import Stock
from app.models.stock_metric import StockMetricDaily
from app.services.indicator_service import (
    calculate_bollinger,
    calculate_break_percent,
    detect_boll_signal,
)
from app.services.longbridge_service import LongbridgeService
from app.services.longbridge_service import SecurityStaticInfo


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
        "trade_date": metric.trade_date.isoformat(),
        "close": close,
        "latest_price": close,
        "market_cap": _to_float(metric.market_cap),
        "avg_volume_1m": _to_float(metric.avg_volume_1m),
        "boll_upper": _to_float(metric.boll_upper),
        "boll_mid": _to_float(metric.boll_mid),
        "boll_lower": _to_float(metric.boll_lower),
        "break_percent": _to_float(metric.break_percent),
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
        for security in provider.list_securities(market_name)
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

    static_info = {info.symbol: info for info in provider.get_static_info(symbols)}
    market_caps = provider.get_market_caps(symbols)

    results: list[dict[str, Any]] = []
    refreshed_at: str | None = None
    for symbol in symbols:
        info = static_info.get(symbol)
        market_cap = market_caps.get(symbol)
        if info is None or market_cap is None or market_cap < min_market_cap:
            continue

        daily_bars = provider.get_daily_bars(symbol, count=30)
        if not daily_bars:
            continue
        avg_volume = sum(bar.volume for bar in daily_bars[-20:]) / min(20, len(daily_bars))
        if Decimal(str(avg_volume)) < min_avg_volume:
            continue

        bars = provider.get_intraday_bars(symbol, interval=interval, limit=30)
        if len(bars) < 21:
            continue
        refreshed_at = bars[-1].time.isoformat()
        closes = [bar.close for bar in bars]
        bands = calculate_bollinger(closes, period=20, std_multiplier=2)
        previous = bands[-2]
        current = bands[-1]
        if None in (previous["upper"], previous["lower"], current["upper"], current["lower"]):
            continue
        current_signal = detect_boll_signal(
            prev_close=closes[-2],
            close=closes[-1],
            prev_upper=float(previous["upper"]),
            upper=float(current["upper"]),
            prev_lower=float(previous["lower"]),
            lower=float(current["lower"]),
        )
        if current_signal == "none" or (signal_type != "all" and signal_type != current_signal):
            continue
        row_market = "US" if symbol.endswith(".US") else "HK"
        results.append(
            {
                "symbol": symbol,
                "name": info.name,
                "market": row_market,
                "currency": _currency(symbol, info),
                "signal_type": current_signal,
                "interval": interval,
                "latest_bar_time": bars[-1].time.isoformat(),
                "close": closes[-1],
                "latest_price": closes[-1],
                "market_cap": _to_float(market_cap),
                "avg_volume_1m": avg_volume,
                "boll_upper": current["upper"],
                "boll_mid": current["mid"],
                "boll_lower": current["lower"],
                "break_percent": calculate_break_percent(
                    current_signal,
                    close=closes[-1],
                    upper=float(current["upper"]),
                    lower=float(current["lower"]),
                ),
                "data_time": bars[-1].time.isoformat(),
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


def _currency(symbol: str, info: SecurityStaticInfo) -> str:
    if info.currency:
        return info.currency
    return "USD" if symbol.endswith(".US") else "HKD"
