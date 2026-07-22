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


class FakeScreenerContext:
    def __init__(self):
        self.calls = []

    def screener_indicators(self):
        self.calls.append(("screener_indicators",))
        return SimpleNamespace(
            data={
                "groups": [
                    {
                        "group_name": "公司规模与财务",
                        "indicators": [
                            {"key": "marketcap", "name": "市值", "unit": "亿"},
                            {"key": "volume", "name": "成交量", "unit": "股"},
                        ],
                    }
                ]
            }
        )

    def screener_search(self, market, strategy_id=None, conditions=None, show=None, page=0, size=20):
        self.calls.append(("screener_search", market, strategy_id, conditions, show, page, size))
        if page == 0:
            return SimpleNamespace(
                data={
                    "total": 2,
                    "items": [
                        {"symbol": "AAPL.US", "name": "Apple"},
                        {"symbol": "MSFT.US", "name": "Microsoft"},
                    ],
                }
            )
        return SimpleNamespace(data={"total": 2, "items": []})


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

    ScreenerCondition = staticmethod(lambda key, min="", max="", tech_values="{}": SimpleNamespace(key=key, min=min, max=max, tech_values=tech_values))


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


def test_longbridge_service_discovers_screener_indicators_before_searching():
    context = FakeScreenerContext()
    service = LongbridgeService(screener_context=context, sdk=FakeSdk)

    securities = service.screen_securities(
        market="US",
        min_market_cap=Decimal("200000000000"),
        min_avg_volume=Decimal("10000000"),
        page_size=50,
    )

    search_call = context.calls[1]
    conditions = search_call[3]
    assert context.calls[0] == ("screener_indicators",)
    assert search_call[:3] == ("screener_search", "US", None)
    assert [(condition.key, condition.min, condition.max) for condition in conditions] == [
        ("marketcap", "2000", ""),
        ("volume", "10000000", ""),
    ]
    assert [security.symbol for security in securities] == ["AAPL.US", "MSFT.US"]
