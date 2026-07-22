from __future__ import annotations

from decimal import Decimal
from math import ceil
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.stock import Stock
from app.models.stock_metric import StockMetricDaily
from app.services.indicator_service import (
    calculate_bollinger,
    calculate_break_percent,
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

    latest_date = session.scalar(select(func.max(StockMetricDaily.trade_date)))
    if latest_date is None:
        return {"data_date": None, "page": page, "page_size": page_size, "total": 0, "results": []}

    base = (
        select(Stock, StockMetricDaily)
        .join(StockMetricDaily, StockMetricDaily.stock_id == Stock.id)
        .where(StockMetricDaily.trade_date == latest_date)
    )
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

    latest_date = session.scalar(select(func.max(StockMetricDaily.trade_date)))
    if latest_date is None:
        return {
            "refreshed_at": None,
            "interval": interval,
            "page": page,
            "page_size": page_size,
            "total": 0,
            "results": [],
        }

    provider = longbridge or LongbridgeService()
    base = (
        select(Stock, StockMetricDaily)
        .join(StockMetricDaily, StockMetricDaily.stock_id == Stock.id)
        .where(StockMetricDaily.trade_date == latest_date)
    )
    candidates = session.execute(
        _apply_filters(base, market, "all", min_market_cap, min_avg_volume)
    ).all()

    results: list[dict[str, Any]] = []
    refreshed_at: str | None = None
    for stock, metric in candidates:
        bars = provider.get_intraday_bars(stock.symbol, interval=interval, limit=30)
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
        results.append(
            {
                "symbol": stock.symbol,
                "name": stock.name,
                "market": stock.market,
                "currency": stock.currency,
                "signal_type": current_signal,
                "interval": interval,
                "latest_bar_time": bars[-1].time.isoformat(),
                "close": closes[-1],
                "latest_price": closes[-1],
                "market_cap": _to_float(metric.market_cap),
                "avg_volume_1m": _to_float(metric.avg_volume_1m),
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
