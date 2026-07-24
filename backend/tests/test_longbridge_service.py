from datetime import date, datetime, timedelta, timezone
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
                symbol=symbol,
                name_cn="腾讯控股" if symbol.endswith(".HK") else "Apple",
                name_en="Tencent" if symbol.endswith(".HK") else "Apple",
                exchange="HKEX" if symbol.endswith(".HK") else "NASDAQ",
                currency="HKD" if symbol.endswith(".HK") else "USD",
                lot_size=100 if symbol.endswith(".HK") else 1,
            )
            for symbol in symbols
        ]

    def calc_indexes(self, symbols, indexes):
        self.calls.append(("calc_indexes", tuple(symbols), tuple(indexes)))
        return [SimpleNamespace(symbol=symbol, total_market_value=Decimal("3600000000000")) for symbol in symbols]

    def quote(self, symbols):
        self.calls.append(("quote", tuple(symbols)))
        base_time = datetime(2026, 7, 21, 20, 0, tzinfo=timezone.utc)
        return [
            SimpleNamespace(
                symbol=symbol,
                last_done=Decimal("100"),
                prev_close=Decimal("99"),
                timestamp=base_time,
                pre_market_quote=SimpleNamespace(
                    last_done=Decimal("101"),
                    prev_close=Decimal("99"),
                    timestamp=base_time - timedelta(hours=1),
                ),
                post_market_quote=SimpleNamespace(
                    last_done=Decimal("102"),
                    prev_close=Decimal("100"),
                    timestamp=base_time + timedelta(hours=1),
                ),
                overnight_quote=SimpleNamespace(
                    last_done=Decimal("103"),
                    prev_close=Decimal("100"),
                    timestamp=base_time + timedelta(hours=2),
                ),
            )
            for symbol in symbols
        ]


class FakeScreenerContext:
    def __init__(self, marketcap_unit="亿", volume_key="volume", volume_name="成交量", volume_unit="股", response_key="items"):
        self.calls = []
        self.marketcap_unit = marketcap_unit
        self.volume_key = volume_key
        self.volume_name = volume_name
        self.volume_unit = volume_unit
        self.response_key = response_key

    def screener_indicators(self):
        self.calls.append(("screener_indicators",))
        return SimpleNamespace(
            data={
                "groups": [
                    {
                        "group_name": "公司规模与财务",
                        "indicators": [
                            {"key": "marketcap", "name": "市值", "unit": self.marketcap_unit},
                            {"key": self.volume_key, "name": self.volume_name, "unit": self.volume_unit},
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
                    self.response_key: [
                        {"symbol": "AAPL.US", "name": "Apple"},
                        {"symbol": "MSFT.US", "name": "Microsoft"},
                    ],
                }
            )
        return SimpleNamespace(data={"total": 2, "items": []})


class FakeCalendarContext:
    def __init__(self):
        self.calls = []

    def finance_calendar(self, category, start, end, market=None):
        self.calls.append(("finance_calendar", category, start, end, market))
        return SimpleNamespace(
            data=[
                SimpleNamespace(symbol="AAPL.US", date="Today 2026.08.18 (EST)"),
                SimpleNamespace(symbol="MSFT.US", date=None, datetime="1787179200"),
                SimpleNamespace(symbol="TSLA.US", date="2026.08.19 (EST)"),
            ]
        )


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

    class CalendarCategory:
        Report = "report"

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


def test_longbridge_service_gets_latest_quote_with_previous_close_from_latest_session():
    context = FakeQuoteContext()
    service = LongbridgeService(quote_context=context, sdk=FakeSdk)

    quotes = service.get_latest_quotes(["AAPL.US"])

    assert context.calls[-1] == ("quote", ("AAPL.US",))
    assert quotes["AAPL.US"].price == 103
    assert quotes["AAPL.US"].previous_close == 100
    assert quotes["AAPL.US"].session == "overnight"
    assert quotes["AAPL.US"].time.isoformat() == "2026-07-21T22:00:00+00:00"


def test_longbridge_service_batches_latest_quote_symbol_requests():
    context = FakeQuoteContext()
    service = LongbridgeService(quote_context=context, sdk=FakeSdk)
    symbols = [f"TEST{index}.US" for index in range(105)]

    quotes = service.get_latest_quotes(symbols)

    quote_calls = [call for call in context.calls if call[0] == "quote"]
    assert [len(call[1]) for call in quote_calls] == [50, 50, 5]
    assert len(quotes) == 105
    assert quotes["TEST104.US"].price == 103


def test_longbridge_service_batches_static_info_and_market_cap_symbol_requests():
    context = FakeQuoteContext()
    service = LongbridgeService(quote_context=context, sdk=FakeSdk)
    symbols = [f"TEST{index}.US" for index in range(105)]

    infos = service.get_static_info(symbols)
    market_caps = service.get_market_caps(symbols)

    static_info_calls = [call for call in context.calls if call[0] == "static_info"]
    calc_index_calls = [call for call in context.calls if call[0] == "calc_indexes"]
    assert [len(call[1]) for call in static_info_calls] == [50, 50, 5]
    assert [len(call[1]) for call in calc_index_calls] == [50, 50, 5]
    assert len(infos) == 105
    assert infos[-1].symbol == "TEST104.US"
    assert len(market_caps) == 105
    assert market_caps["TEST104.US"] == Decimal("3600000000000")


def test_longbridge_service_gets_earnings_dates_from_single_daily_calendar_call():
    context = FakeCalendarContext()
    service = LongbridgeService(calendar_context=context, sdk=FakeSdk)

    earnings_dates = service.get_earnings_dates(
        ["AAPL.US", "WMT.US"],
        market="US",
        reference_date=date(2026, 8, 18),
    )

    assert context.calls == [
        ("finance_calendar", "report", "2026-08-18", "2026-08-18", "US"),
    ]
    assert earnings_dates == {"AAPL.US": date(2026, 8, 18)}


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


def test_longbridge_service_retries_screener_search_when_rate_limited():
    class RateLimitedScreenerContext(FakeScreenerContext):
        def __init__(self):
            super().__init__()
            self.search_attempts = 0

        def screener_search(self, market, strategy_id=None, conditions=None, show=None, page=0, size=20):
            self.search_attempts += 1
            if self.search_attempts == 1:
                raise RuntimeError("OpenApiException: code=429002 api request is limited, please slow down request frequency")
            return super().screener_search(market, strategy_id, conditions, show, page, size)

    sleeps: list[float] = []
    context = RateLimitedScreenerContext()
    service = LongbridgeService(screener_context=context, sdk=FakeSdk, sleep=sleeps.append)

    securities = service.screen_securities(
        market="US",
        min_market_cap=Decimal("200000000000"),
        min_avg_volume=Decimal("10000000"),
        page_size=50,
    )

    assert sleeps == [1]
    assert context.search_attempts == 2
    assert [security.symbol for security in securities] == ["AAPL.US", "MSFT.US"]


def test_longbridge_service_converts_screener_condition_values_by_indicator_unit():
    context = FakeScreenerContext(
        marketcap_unit="B",
        volume_key="onemonthamount",
        volume_name="1 Month Volume",
        volume_unit="K",
    )
    service = LongbridgeService(screener_context=context, sdk=FakeSdk)

    service.screen_securities(
        market="US",
        min_market_cap=Decimal("50000000000"),
        min_avg_volume=Decimal("5000000"),
        page_size=50,
    )

    conditions = context.calls[1][3]
    assert [(condition.key, condition.min, condition.max) for condition in conditions] == [
        ("marketcap", "50", ""),
        ("onemonthamount", "5000", ""),
    ]


def test_longbridge_service_prefers_month_volume_indicator_over_generic_volume():
    class AmbiguousVolumeScreenerContext(FakeScreenerContext):
        def screener_indicators(self):
            self.calls.append(("screener_indicators",))
            return SimpleNamespace(
                data={
                    "groups": [
                        {
                            "group_name": "Company",
                            "indicators": [
                                {"key": "marketcap", "name": "Market Cap", "unit": "B"},
                                {"key": "total_amount", "name": "Volume", "unit": "K"},
                                {"key": "onemonthamount", "name": "1 Month Volume", "unit": "K"},
                            ],
                        }
                    ]
                }
            )

    context = AmbiguousVolumeScreenerContext()
    service = LongbridgeService(screener_context=context, sdk=FakeSdk)

    service.screen_securities(
        market="US",
        min_market_cap=Decimal("50000000000"),
        min_avg_volume=Decimal("8000000"),
        page_size=50,
    )

    conditions = context.calls[1][3]
    assert [(condition.key, condition.min, condition.max) for condition in conditions] == [
        ("marketcap", "50", ""),
        ("onemonthamount", "8000", ""),
    ]


def test_longbridge_service_parses_counter_id_and_alternate_item_list_key():
    class CounterIdScreenerContext(FakeScreenerContext):
        def __init__(self):
            super().__init__(response_key="lists")

        def screener_search(self, market, strategy_id=None, conditions=None, show=None, page=0, size=20):
            self.calls.append(("screener_search", market, strategy_id, conditions, show, page, size))
            if page == 0:
                return SimpleNamespace(
                    data={
                        "total": 1,
                        "lists": [
                            {
                                "counter_id": "ST/HK/00700",
                                "name": "腾讯控股",
                                "indicators": [
                                    {"key": "marketcap", "value": "3600000000000"},
                                ],
                            }
                        ],
                    }
                )
            return SimpleNamespace(data={"total": 1, "lists": []})

    context = CounterIdScreenerContext()
    service = LongbridgeService(screener_context=context, sdk=FakeSdk)

    securities = service.screen_securities(
        market="HK",
        min_market_cap=Decimal("200000000000"),
        min_avg_volume=Decimal("10000000"),
        page_size=50,
    )

    assert securities[0].symbol == "700.HK"
    assert securities[0].name == "腾讯控股"
    assert securities[0].market_cap == Decimal("3600000000000")
