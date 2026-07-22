from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.daily_bar import DailyBar
from app.models.request_log import RequestLog
from app.models.screening_run import ScreeningRun
from app.models.stock import Stock
from app.models.stock_metric import StockMetricDaily


def make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_models_persist_stock_metric_and_request_log():
    session = make_session()
    now = datetime.now(timezone.utc)
    stock = Stock(
        symbol="00700.HK",
        name="腾讯控股",
        market="HK",
        currency="HKD",
        exchange="HKEX",
        lot_size=100,
        status="active",
        created_at=now,
        updated_at=now,
    )
    session.add(stock)
    session.flush()

    session.add(
        DailyBar(
            stock_id=stock.id,
            trade_date=date(2026, 7, 21),
            open=Decimal("380.0"),
            high=Decimal("390.0"),
            low=Decimal("378.0"),
            close=Decimal("388.0"),
            volume=12_000_000,
            turnover=Decimal("4500000000"),
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        StockMetricDaily(
            stock_id=stock.id,
            trade_date=date(2026, 7, 21),
            close=Decimal("388.0"),
            market_cap=Decimal("3600000000000"),
            avg_volume_1m=Decimal("21000000"),
            boll_period=20,
            boll_std_multiplier=Decimal("2"),
            boll_mid=Decimal("365.1"),
            boll_upper=Decimal("386.2"),
            boll_lower=Decimal("344.0"),
            prev_close=Decimal("380.0"),
            prev_boll_upper=Decimal("385.0"),
            prev_boll_lower=Decimal("345.0"),
            signal_type="upper_breakout",
            break_percent=Decimal("0.00466"),
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        ScreeningRun(
            run_date=date(2026, 7, 21),
            status="success",
            markets="US,HK",
            boll_period=20,
            boll_std_multiplier=Decimal("2"),
            started_at=now,
            finished_at=now,
            stock_count=1,
            metrics_count=1,
            signal_count=1,
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        RequestLog(
            request_id="req-1",
            client_ip="127.0.0.1",
            method="GET",
            path="/api/daily-screenings",
            query_params="market=HK",
            response_status=200,
            response_body='{"success":true}',
            duration_ms=12,
            user_agent="pytest",
            created_at=now,
        )
    )
    session.commit()

    metric = session.scalar(select(StockMetricDaily).where(StockMetricDaily.stock_id == stock.id))
    log = session.scalar(select(RequestLog).where(RequestLog.request_id == "req-1"))

    assert metric.signal_type == "upper_breakout"
    assert metric.stock.symbol == "00700.HK"
    assert log.path == "/api/daily-screenings"
