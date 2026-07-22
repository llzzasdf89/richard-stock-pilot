from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.services.longbridge_service import LongbridgeService


class FakeQuoteContext:
    def __init__(self):
        self.calls = []

    def candlesticks(self, symbol, period, count, adjust_type):
        self.calls.append(("candlesticks", symbol, period, count, adjust_type))
        return [
            SimpleNamespace(
                timestamp=datetime(2026, 7, 21, tzinfo=timezone.utc),
                open=Decimal("100"),
                high=Decimal("110"),
                low=Decimal("99"),
                close=Decimal("108"),
                volume=123456,
                turnover=Decimal("1234567"),
            )
        ]

    def security_list(self, market):
        self.calls.append(("security_list", market))
        return [SimpleNamespace(symbol="700.HK", name_cn="腾讯控股", name_en="Tencent")]

    def static_info(self, symbols):
        self.calls.append(("static_info", tuple(symbols)))
        return [
            SimpleNamespace(
                symbol="700.HK",
                name_cn="腾讯控股",
                name_en="Tencent",
                exchange="HKEX",
                currency="HKD",
                lot_size=100,
            )
        ]

    def calc_indexes(self, symbols, indexes):
        self.calls.append(("calc_indexes", tuple(symbols), tuple(indexes)))
        return [SimpleNamespace(symbol="700.HK", total_market_value=Decimal("3600000000000"))]


class FakeSdk:
    class Period:
        Day = "day"
        Min_5 = "5m"

    class AdjustType:
        NoAdjust = "no_adjust"

    class Market:
        HK = "HK"
        US = "US"

    class CalcIndex:
        TotalMarketValue = "total_market_value"


def test_longbridge_service_treats_blank_credentials_as_unconfigured(monkeypatch):
    monkeypatch.setenv("LONGBRIDGE_APP_KEY", "")
    monkeypatch.setenv("LONGBRIDGE_APP_SECRET", "")
    monkeypatch.setenv("LONGBRIDGE_ACCESS_TOKEN", "")

    service = LongbridgeService()

    bars = service.get_intraday_bars("AAPL.US", interval="5m", limit=30)
    assert len(bars) == 30
    assert bars[-1].close > bars[0].close


def test_longbridge_service_maps_daily_candlesticks_from_sdk_context():
    context = FakeQuoteContext()
    service = LongbridgeService(quote_context=context, sdk=FakeSdk)

    bars = service.get_daily_bars("700.HK", count=1)

    assert bars[0].close == 108
    assert bars[0].volume == 123456
    assert bars[0].time.isoformat() == "2026-07-21T00:00:00+00:00"
    assert context.calls[0] == ("candlesticks", "700.HK", "day", 1, "no_adjust")


def test_longbridge_service_maps_intraday_interval_to_sdk_period():
    context = FakeQuoteContext()
    service = LongbridgeService(quote_context=context, sdk=FakeSdk)

    bars = service.get_intraday_bars("700.HK", interval="5m", limit=1)

    assert bars[0].close == 108
    assert context.calls[0] == ("candlesticks", "700.HK", "5m", 1, "no_adjust")


def test_longbridge_service_maps_security_list_and_static_info():
    context = FakeQuoteContext()
    service = LongbridgeService(quote_context=context, sdk=FakeSdk)

    securities = service.list_securities("HK")
    info = service.get_static_info(["700.HK"])

    assert securities[0].symbol == "700.HK"
    assert securities[0].name == "腾讯控股"
    assert info[0].currency == "HKD"
    assert info[0].lot_size == 100


def test_longbridge_service_fetches_market_cap_via_calc_indexes():
    context = FakeQuoteContext()
    service = LongbridgeService(quote_context=context, sdk=FakeSdk)

    market_caps = service.get_market_caps(["700.HK"])

    assert market_caps["700.HK"] == Decimal("3600000000000")
