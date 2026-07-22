from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models.base import Base
from app.models.request_log import RequestLog
from app.models.stock import Stock
from app.models.stock_metric import StockMetricDaily


def build_client(monkeypatch=None) -> tuple[TestClient, sessionmaker[Session]]:
    if monkeypatch is not None:
        for name in (
            "LONGBRIDGE_APP_KEY",
            "LONGBRIDGE_APP_SECRET",
            "LONGBRIDGE_ACCESS_TOKEN",
        ):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setattr("app.services.longbridge_service.load_environment", lambda: None)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        session = testing_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.state.session_factory = testing_session
    return TestClient(app), testing_session


def seed_metric(session: Session) -> None:
    now = datetime.now(timezone.utc)
    stock = Stock(
        symbol="AAPL.US",
        name="Apple",
        market="US",
        currency="USD",
        exchange="NASDAQ",
        lot_size=1,
        status="active",
        created_at=now,
        updated_at=now,
    )
    session.add(stock)
    session.flush()
    session.add(
        StockMetricDaily(
            stock_id=stock.id,
            trade_date=date(2026, 7, 21),
            close=Decimal("210.50"),
            market_cap=Decimal("3200000000000"),
            avg_volume_1m=Decimal("54000000"),
            boll_period=20,
            boll_std_multiplier=Decimal("2"),
            boll_mid=Decimal("200.00"),
            boll_upper=Decimal("208.00"),
            boll_lower=Decimal("192.00"),
            prev_close=Decimal("206.00"),
            prev_boll_upper=Decimal("207.00"),
            prev_boll_lower=Decimal("193.00"),
            signal_type="upper_breakout",
            break_percent=Decimal("0.012019"),
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


def seed_cross_market_metrics(session: Session) -> None:
    seed_metric(session)
    now = datetime.now(timezone.utc)
    stock = Stock(
        symbol="700.HK",
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
        StockMetricDaily(
            stock_id=stock.id,
            trade_date=date(2026, 7, 22),
            close=Decimal("520.00"),
            market_cap=Decimal("4000000000000"),
            avg_volume_1m=Decimal("36000000"),
            boll_period=20,
            boll_std_multiplier=Decimal("2"),
            boll_mid=Decimal("500.00"),
            boll_upper=Decimal("515.00"),
            boll_lower=Decimal("455.00"),
            prev_close=Decimal("510.00"),
            prev_boll_upper=Decimal("514.00"),
            prev_boll_lower=Decimal("456.00"),
            signal_type="upper_breakout",
            break_percent=Decimal("0.009709"),
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


def test_daily_screenings_return_unified_response_and_log_request(monkeypatch):
    client, session_factory = build_client(monkeypatch)
    with session_factory() as session:
        seed_metric(session)

    response = client.get(
        "/api/daily-screenings",
        params={"market": "US", "min_market_cap": "200000000000", "page": 1, "page_size": 20},
        headers={"X-Request-ID": "req-daily-1", "User-Agent": "pytest"},
    )

    body = response.json()
    row = body["data"]["results"][0]
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-daily-1"
    assert body["success"] is True
    assert body["code"] == 200
    assert body["data"]["total"] == 1
    assert row["symbol"] == "AAPL.US"
    assert row["latest_price"] == row["close"] == 210.5
    assert row["boll_upper"] == 208
    assert row["boll_mid"] == 200
    assert row["boll_lower"] == 192

    with session_factory() as session:
        log = session.scalar(select(RequestLog).where(RequestLog.request_id == "req-daily-1"))
        assert log is not None
        assert log.path == "/api/daily-screenings"
        assert log.response_status == 200
        assert "min_market_cap=200000000000" in log.query_params
        assert '"success":true' in log.response_body


def test_daily_screenings_use_latest_trade_date_per_market_when_market_is_all(monkeypatch):
    client, session_factory = build_client(monkeypatch)
    with session_factory() as session:
        seed_cross_market_metrics(session)

    response = client.get(
        "/api/daily-screenings",
        params={
            "market": "all",
            "signal_type": "all",
            "min_market_cap": "200000000000",
            "min_avg_volume": "10000000",
            "page": 1,
            "page_size": 20,
        },
        headers={"X-Request-ID": "req-daily-cross-market"},
    )

    body = response.json()
    symbols = {row["symbol"] for row in body["data"]["results"]}
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["total"] == 2
    assert symbols == {"AAPL.US", "700.HK"}


def test_intraday_screenings_fetch_latest_market_data_without_daily_metrics(monkeypatch):
    client, _ = build_client(monkeypatch)

    response = client.get(
        "/api/intraday-screenings",
        params={
            "market": "US",
            "signal_type": "upper_breakout",
            "min_market_cap": "200000000000",
            "min_avg_volume": "10000000",
            "interval": "5m",
            "page": 1,
            "page_size": 10,
        },
        headers={"X-Request-ID": "req-intraday-1"},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["success"] is True
    assert body["code"] == 200
    assert body["data"]["interval"] == "5m"
    assert body["data"]["total"] == 1
    assert body["data"]["results"][0]["symbol"] == "AAPL.US"
    assert body["data"]["results"][0]["latest_price"] > body["data"]["results"][0]["boll_upper"]


def test_intraday_screenings_passes_slider_filters_to_longbridge_screener(monkeypatch):
    call_symbols: list[str] = []
    screen_calls: list[tuple[str, Decimal, Decimal]] = []

    class FakeLongbridge:
        def screen_securities(self, market, min_market_cap, min_avg_volume):
            from app.services.longbridge_service import Security

            screen_calls.append((market, min_market_cap, min_avg_volume))
            return [
                Security(symbol="AAPL.US", name="Apple", market_cap=Decimal("3000000000000")),
            ]

        def get_daily_bars(self, symbol, count=30):
            from app.services.longbridge_service import MarketDataBar

            now = datetime.now(timezone.utc)
            return [
                MarketDataBar(
                    time=now,
                    open=100,
                    high=101,
                    low=99,
                    close=100 + index,
                    volume=20_000_000,
                    turnover=Decimal("100000000"),
                )
                for index in range(25)
            ]

        def get_intraday_bars(self, symbol, interval="5m", limit=30):
            from app.services.longbridge_service import IntradayBar

            call_symbols.append(symbol)
            now = datetime.now(timezone.utc)
            return [
                IntradayBar(time=now, close=200 + index * 0.2 if index < limit - 1 else 208)
                for index in range(limit)
            ]

    monkeypatch.setattr("app.services.screening_service.LongbridgeService", lambda: FakeLongbridge())
    client, _ = build_client(monkeypatch)

    response = client.get(
        "/api/intraday-screenings",
        params={
            "market": "US",
            "signal_type": "all",
            "min_market_cap": "200000000000",
            "min_avg_volume": "10000000",
            "interval": "5m",
            "page": 1,
            "page_size": 10,
        },
        headers={"X-Request-ID": "req-intraday-market-cap"},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["success"] is True
    assert screen_calls == [("US", Decimal("200000000000"), Decimal("10000000"))]
    assert call_symbols == ["AAPL.US"]


def test_internal_errors_still_return_http_200_with_code_500(monkeypatch):
    client, _ = build_client(monkeypatch)

    response = client.get(
        "/api/daily-screenings",
        params={"page": 0},
        headers={"X-Request-ID": "req-error-1"},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["success"] is False
    assert body["code"] == 500
    assert body["data"]["request_id"] == "req-error-1"


def test_validation_errors_follow_unified_response_contract(monkeypatch):
    client, _ = build_client(monkeypatch)

    response = client.get(
        "/api/daily-screenings",
        params={"min_market_cap": "not-a-number"},
        headers={"X-Request-ID": "req-validation-1"},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["success"] is False
    assert body["code"] == 500
    assert body["data"]["request_id"] == "req-validation-1"
