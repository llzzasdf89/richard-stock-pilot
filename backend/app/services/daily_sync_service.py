from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.daily_bar import DailyBar
from app.models.screening_run import ScreeningRun
from app.models.stock import Stock
from app.models.stock_metric import StockMetricDaily
from app.services.indicator_service import (
    DailyPriceBar,
    calculate_bollinger,
    calculate_break_percent,
    calculate_historical_setup,
    detect_boll_signal,
)
from app.services.longbridge_service import LongbridgeService, MarketDataBar


def has_daily_screening_data(session: Session, target_date: date) -> bool:
    return (
        session.scalar(
            select(StockMetricDaily.id)
            .where(StockMetricDaily.trade_date == target_date)
            .limit(1)
        )
        is not None
    )


def sync_daily_screening(
    session: Session,
    symbols: list[str],
    longbridge: LongbridgeService | None = None,
    boll_period: int = 20,
    boll_std_multiplier: Decimal = Decimal("2"),
    bar_count: int = 60,
) -> dict[str, Any]:
    provider = longbridge or LongbridgeService()
    now = datetime.now(timezone.utc)
    run = ScreeningRun(
        run_date=now.date(),
        status="running",
        markets="US,HK",
        boll_period=boll_period,
        boll_std_multiplier=boll_std_multiplier,
        started_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(run)
    session.flush()

    metrics_count = 0
    signal_count = 0
    try:
        static_info = {info.symbol: info for info in provider.get_static_info(symbols)}
        market_caps = provider.get_market_caps(symbols)
        bars_by_symbol: dict[str, list[MarketDataBar]] = {}
        reference_dates: dict[str, date] = {}
        for symbol in symbols:
            bars = provider.get_daily_bars(symbol, count=bar_count)
            bars_by_symbol[symbol] = bars
            if bars:
                reference_dates[symbol] = bars[-1].time.date()
        earnings_dates = _get_earnings_dates(provider, symbols, reference_dates)
        for symbol in symbols:
            info = static_info.get(symbol)
            if info is None:
                continue
            stock = _upsert_stock(session, symbol, info, earnings_dates.get(symbol), now)
            bars = bars_by_symbol.get(symbol, [])
            if len(bars) < boll_period + 1:
                continue
            _upsert_daily_bars(session, stock.id, bars, now)
            metric = _build_metric(
                stock_id=stock.id,
                bars=bars,
                market_cap=market_caps.get(symbol),
                boll_period=boll_period,
                boll_std_multiplier=boll_std_multiplier,
                now=now,
            )
            if metric is None:
                continue
            _upsert_metric(session, metric)
            metrics_count += 1
            if metric.signal_type != "none":
                signal_count += 1

        run.status = "success"
        run.finished_at = datetime.now(timezone.utc)
        run.stock_count = len(symbols)
        run.metrics_count = metrics_count
        run.signal_count = signal_count
        run.updated_at = datetime.now(timezone.utc)
        session.commit()
        return {
            "run_id": run.id,
            "stock_count": len(symbols),
            "metrics_count": metrics_count,
            "signal_count": signal_count,
        }
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        run.updated_at = datetime.now(timezone.utc)
        session.commit()
        raise


def _get_earnings_dates(
    provider: LongbridgeService,
    symbols: list[str],
    reference_dates: dict[str, date],
) -> dict[str, date]:
    get_dates = getattr(provider, "get_earnings_dates", None)
    if get_dates is None:
        return {}
    earnings_dates: dict[str, date] = {}
    for market in ("US", "HK"):
        market_symbols = [symbol for symbol in symbols if symbol.endswith(f".{market}") and symbol in reference_dates]
        dates = sorted({reference_dates[symbol] for symbol in market_symbols})
        for reference_date in dates:
            date_symbols = [symbol for symbol in market_symbols if reference_dates[symbol] == reference_date]
            earnings_dates.update(get_dates(date_symbols, market=market, reference_date=reference_date))
    return earnings_dates


def _upsert_stock(session: Session, symbol: str, info: Any, earnings_date: date | None, now: datetime) -> Stock:
    stock = session.scalar(select(Stock).where(Stock.symbol == symbol))
    market = "US" if symbol.endswith(".US") else "HK"
    if stock is None:
        stock = Stock(
            symbol=symbol,
            name=info.name,
            market=market,
            currency=info.currency or ("USD" if market == "US" else "HKD"),
            exchange=info.exchange,
            lot_size=info.lot_size,
            status="active",
            earnings_date=earnings_date,
            created_at=now,
            updated_at=now,
        )
        session.add(stock)
        session.flush()
        return stock

    stock.name = info.name
    stock.market = market
    stock.currency = info.currency or stock.currency
    stock.exchange = info.exchange
    stock.lot_size = info.lot_size
    stock.status = "active"
    stock.earnings_date = earnings_date
    stock.updated_at = now
    return stock


def _upsert_daily_bars(session: Session, stock_id: int, bars: list[MarketDataBar], now: datetime) -> None:
    for bar in bars:
        trade_date = bar.time.date()
        existing = session.scalar(
            select(DailyBar).where(DailyBar.stock_id == stock_id, DailyBar.trade_date == trade_date)
        )
        if existing is None:
            session.add(
                DailyBar(
                    stock_id=stock_id,
                    trade_date=trade_date,
                    open=Decimal(str(bar.open)),
                    high=Decimal(str(bar.high)),
                    low=Decimal(str(bar.low)),
                    close=Decimal(str(bar.close)),
                    volume=bar.volume,
                    turnover=bar.turnover,
                    created_at=now,
                    updated_at=now,
                )
            )
            continue
        existing.open = Decimal(str(bar.open))
        existing.high = Decimal(str(bar.high))
        existing.low = Decimal(str(bar.low))
        existing.close = Decimal(str(bar.close))
        existing.volume = bar.volume
        existing.turnover = bar.turnover
        existing.updated_at = now


def _build_metric(
    stock_id: int,
    bars: list[MarketDataBar],
    market_cap: Decimal | None,
    boll_period: int,
    boll_std_multiplier: Decimal,
    now: datetime,
) -> StockMetricDaily | None:
    if market_cap is None:
        return None
    closes = [bar.close for bar in bars]
    historical_bars = [
        DailyPriceBar(
            trade_date=bar.time.date(),
            high=bar.high,
            low=bar.low,
            close=bar.close,
        )
        for bar in bars[:-1]
    ]
    setup = calculate_historical_setup(
        historical_bars,
        current_price=closes[-1],
        boll_period=boll_period,
        boll_std_multiplier=float(boll_std_multiplier),
    )
    historical_bands = calculate_bollinger(
        closes[:-1],
        period=boll_period,
        std_multiplier=float(boll_std_multiplier),
    )
    prev_band = historical_bands[-2]
    current_band = {
        "mid": setup.boll_mid,
        "upper": setup.boll_upper,
        "lower": setup.boll_lower,
    }
    if None in (
        prev_band["upper"],
        prev_band["lower"],
        current_band["mid"],
        current_band["upper"],
        current_band["lower"],
    ):
        return None
    signal_type = detect_boll_signal(
        prev_close=closes[-2],
        close=closes[-1],
        prev_upper=float(prev_band["upper"]),
        upper=float(current_band["upper"]),
        prev_lower=float(prev_band["lower"]),
        lower=float(current_band["lower"]),
    )
    avg_volume = sum(bar.volume for bar in bars[-20:]) / min(20, len(bars))
    return StockMetricDaily(
        stock_id=stock_id,
        trade_date=bars[-1].time.date(),
        close=Decimal(str(closes[-1])),
        market_cap=market_cap,
        avg_volume_1m=Decimal(str(avg_volume)),
        boll_period=boll_period,
        boll_std_multiplier=boll_std_multiplier,
        boll_mid=Decimal(str(current_band["mid"])),
        boll_upper=Decimal(str(current_band["upper"])),
        boll_lower=Decimal(str(current_band["lower"])),
        prev_close=Decimal(str(closes[-2])),
        prev_boll_upper=Decimal(str(prev_band["upper"])),
        prev_boll_lower=Decimal(str(prev_band["lower"])),
        signal_type=signal_type,
        break_percent=_decimal_or_none(
            calculate_break_percent(
                signal_type,
                close=closes[-1],
                upper=float(current_band["upper"]),
                lower=float(current_band["lower"]),
            )
        ),
        ma20_direction=setup.ma20_direction,
        atr14=_decimal_or_none(setup.atr14),
        previous_10d_low=_decimal_or_none(setup.previous_10d_low),
        previous_10d_high=_decimal_or_none(setup.previous_10d_high),
        has_reversal_trend=setup.has_reversal_trend,
        is_suitable_for_entry=setup.is_suitable_for_entry,
        created_at=now,
        updated_at=now,
    )


def _upsert_metric(session: Session, metric: StockMetricDaily) -> None:
    existing = session.scalar(
        select(StockMetricDaily).where(
            StockMetricDaily.stock_id == metric.stock_id,
            StockMetricDaily.trade_date == metric.trade_date,
            StockMetricDaily.boll_period == metric.boll_period,
            StockMetricDaily.boll_std_multiplier == metric.boll_std_multiplier,
        )
    )
    if existing is None:
        session.add(metric)
        return
    for field in (
        "close",
        "market_cap",
        "avg_volume_1m",
        "boll_mid",
        "boll_upper",
        "boll_lower",
        "prev_close",
        "prev_boll_upper",
        "prev_boll_lower",
        "signal_type",
        "break_percent",
        "ma20_direction",
        "atr14",
        "previous_10d_low",
        "previous_10d_high",
        "has_reversal_trend",
        "is_suitable_for_entry",
        "updated_at",
    ):
        setattr(existing, field, getattr(metric, field))


def _decimal_or_none(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))
