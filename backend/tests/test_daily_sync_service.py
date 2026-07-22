from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.daily_bar import DailyBar
from app.models.screening_run import ScreeningRun
from app.models.stock import Stock
from app.models.stock_metric import StockMetricDaily
from app.services.daily_sync_service import sync_daily_screening
from app.services.daily_sync_service import has_daily_screening_data
from app.services.longbridge_service import MarketDataBar, SecurityStaticInfo


class FakeLongbridge:
    def get_static_info(self, symbols):
        return [
            SecurityStaticInfo(
                symbol="AAPL.US",
                name="Apple",
                exchange="NASDAQ",
                currency="USD",
                lot_size=1,
            )
        ]

    def get_market_caps(self, symbols):
        return {"AAPL.US": Decimal("3200000000000")}

    def get_daily_bars(self, symbol, count=60):
        start = datetime(2026, 6, 27, tzinfo=timezone.utc)
        bars = []
        for index in range(25):
            close = 100 + index
            if index == 24:
                close = 140
            bars.append(
                MarketDataBar(
                    time=start + timedelta(days=index),
                    open=float(close - 1),
                    high=float(close + 1),
                    low=float(close - 2),
                    close=float(close),
                    volume=20_000_000 + index,
                    turnover=Decimal("100000000"),
                )
            )
        return bars


def test_sync_daily_screening_persists_stock_bars_metrics_and_run():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)

    result = sync_daily_screening(session, ["AAPL.US"], longbridge=FakeLongbridge())

    stock = session.scalar(select(Stock).where(Stock.symbol == "AAPL.US"))
    metric = session.scalar(select(StockMetricDaily).where(StockMetricDaily.stock_id == stock.id))
    run = session.scalar(select(ScreeningRun))
    bars = session.scalars(select(DailyBar).where(DailyBar.stock_id == stock.id)).all()

    assert result["stock_count"] == 1
    assert stock.currency == "USD"
    assert len(bars) == 25
    assert metric.market_cap == Decimal("3200000000000")
    assert metric.avg_volume_1m > 20_000_000
    assert metric.signal_type == "upper_breakout"
    assert run.status == "success"
    assert run.signal_count == 1


def test_has_daily_screening_data_checks_target_date():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)

    assert has_daily_screening_data(session, date(2026, 7, 22)) is False

    sync_daily_screening(session, ["AAPL.US"], longbridge=FakeLongbridge())

    assert has_daily_screening_data(session, date(2026, 7, 21)) is True
    assert has_daily_screening_data(session, date(2026, 7, 22)) is False
