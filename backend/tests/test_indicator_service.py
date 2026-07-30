from datetime import date, timedelta

import pytest

from app.services.indicator_service import (
    DailyPriceBar,
    calculate_bollinger,
    calculate_break_percent,
    calculate_historical_setup,
    calculate_true_range,
    detect_boll_signal,
)


def test_calculate_bollinger_returns_none_until_period_is_reached():
    bands = calculate_bollinger([10, 11, 12], period=3, std_multiplier=2)

    assert bands[0] == {"mid": None, "upper": None, "lower": None}
    assert bands[1] == {"mid": None, "upper": None, "lower": None}
    assert bands[2]["mid"] == 11


def test_calculate_bollinger_uses_population_standard_deviation():
    bands = calculate_bollinger([10, 11, 12], period=3, std_multiplier=2)

    assert round(bands[2]["upper"], 6) == round(11 + 2 * (2 / 3) ** 0.5, 6)
    assert round(bands[2]["lower"], 6) == round(11 - 2 * (2 / 3) ** 0.5, 6)


def test_detect_boll_signal_identifies_upper_breakout():
    signal = detect_boll_signal(
        prev_close=99,
        close=103,
        prev_upper=100,
        upper=102,
        prev_lower=90,
        lower=92,
    )

    assert signal == "upper_breakout"


def test_detect_boll_signal_identifies_lower_breakdown():
    signal = detect_boll_signal(
        prev_close=101,
        close=94,
        prev_upper=110,
        upper=108,
        prev_lower=100,
        lower=95,
    )

    assert signal == "lower_breakdown"


def test_detect_boll_signal_returns_none_when_no_cross():
    signal = detect_boll_signal(
        prev_close=101,
        close=102,
        prev_upper=100,
        upper=103,
        prev_lower=90,
        lower=92,
    )

    assert signal == "none"


def test_calculate_break_percent_uses_matching_band():
    assert calculate_break_percent("upper_breakout", close=105, upper=100, lower=90) == 0.05
    assert calculate_break_percent("lower_breakdown", close=90, upper=110, lower=100) == 0.1
    assert calculate_break_percent("none", close=100, upper=110, lower=90) is None


def _daily_bars(closes: list[float], spread: float = 1) -> list[DailyPriceBar]:
    start = date(2026, 1, 1)
    return [
        DailyPriceBar(
            trade_date=start + timedelta(days=index),
            high=close + spread,
            low=close - spread,
            close=close,
        )
        for index, close in enumerate(closes)
    ]


def test_calculate_historical_setup_uses_trading_day_windows():
    bars = _daily_bars([float(value) for value in range(100, 125)])

    result = calculate_historical_setup(bars, current_price=126)

    assert result.ma20_direction == "上升"
    assert result.previous_10d_low == 114
    assert result.previous_10d_high == 125
    assert result.boll_mid == 114.5


def test_calculate_historical_setup_deduplicates_and_sorts_dates():
    bars = _daily_bars([float(value) for value in range(100, 125)])
    duplicate = DailyPriceBar(
        trade_date=bars[-1].trade_date,
        high=999,
        low=999,
        close=999,
    )

    result = calculate_historical_setup([duplicate, *reversed(bars)], current_price=126)

    assert result.previous_10d_low == 114
    assert result.previous_10d_high == 125


def test_calculate_historical_setup_identifies_down_and_flat_ma20():
    down = calculate_historical_setup(_daily_bars([float(value) for value in range(125, 100, -1)]), 99)
    flat = calculate_historical_setup(_daily_bars([100.0] * 25), 100)

    assert down.ma20_direction == "下降"
    assert flat.ma20_direction == "需人工判断"
    assert flat.has_reversal_trend == "否"
    assert flat.is_suitable_for_entry == "否"


def test_calculate_true_range_uses_standard_maximum():
    assert calculate_true_range(high=12, low=9, previous_close=10) == 3
    assert calculate_true_range(high=15, low=14, previous_close=10) == 5
    assert calculate_true_range(high=9, low=7, previous_close=12) == 5


def test_calculate_historical_setup_averages_fourteen_true_ranges():
    bars = _daily_bars([100.0] * 25, spread=2)

    result = calculate_historical_setup(bars, current_price=100)

    assert result.atr14 == 4


def test_calculate_historical_setup_calculates_population_z_score():
    bars = _daily_bars([float(value) for value in range(1, 26)])

    result = calculate_historical_setup(bars, current_price=30)

    expected_ma = 15.5
    expected_sd = (665 / 20) ** 0.5
    assert result.z_score == pytest.approx((30 - expected_ma) / expected_sd)


def test_calculate_historical_setup_returns_zero_z_score_when_sd20_is_zero():
    result = calculate_historical_setup(
        _daily_bars([100.0] * 25),
        current_price=120,
    )

    assert result.z_score == 0


def test_calculate_historical_setup_uses_negative_z_threshold_without_boll_for_long_entry():
    bars = _daily_bars([float(value) for value in range(100, 125)])
    bars[-10:] = [
        DailyPriceBar(bar.trade_date, high=bar.high, low=80, close=bar.close)
        for bar in bars[-10:]
    ]
    ma20 = 114.5
    sd20 = (665 / 20) ** 0.5
    threshold_price = ma20 - 1.5 * sd20
    entry = calculate_historical_setup(bars, current_price=threshold_price)

    assert entry.boll_lower is not None
    assert threshold_price > entry.boll_lower
    assert entry.z_score == -1.5
    assert entry.has_reversal_trend == "否"
    assert entry.is_suitable_for_entry == "是"


def test_calculate_historical_setup_detects_long_reversal_using_z_threshold():
    bars = _daily_bars([float(value) for value in range(100, 125)])
    bars[-10:] = [
        DailyPriceBar(bar.trade_date, high=bar.high, low=80, close=bar.close)
        for bar in bars[-10:]
    ]
    baseline = calculate_historical_setup(bars, current_price=0)
    assert baseline.boll_lower is not None
    assert baseline.previous_10d_low is not None
    assert baseline.atr14 is not None

    reversal_price = min(
        114.5 - 1.5 * (665 / 20) ** 0.5,
        baseline.previous_10d_low - 0.25 * baseline.atr14 - 0.01,
    )
    reversal = calculate_historical_setup(bars, current_price=reversal_price)

    assert reversal.has_reversal_trend == "是"
    assert reversal.is_suitable_for_entry == "否"


def test_calculate_historical_setup_uses_positive_z_threshold_without_boll_for_short_entry():
    bars = _daily_bars([float(value) for value in range(125, 100, -1)])
    bars[-10:] = [
        DailyPriceBar(bar.trade_date, high=145, low=bar.low, close=bar.close)
        for bar in bars[-10:]
    ]
    ma20 = 110.5
    sd20 = (665 / 20) ** 0.5
    threshold_price = ma20 + 1.5 * sd20
    entry = calculate_historical_setup(bars, current_price=threshold_price)

    assert entry.boll_upper is not None
    assert threshold_price < entry.boll_upper
    assert entry.z_score == 1.5
    assert entry.has_reversal_trend == "否"
    assert entry.is_suitable_for_entry == "是"


def test_calculate_historical_setup_detects_short_reversal_using_z_threshold():
    bars = _daily_bars([float(value) for value in range(125, 100, -1)])
    bars[-10:] = [
        DailyPriceBar(bar.trade_date, high=145, low=bar.low, close=bar.close)
        for bar in bars[-10:]
    ]
    baseline = calculate_historical_setup(bars, current_price=999)
    assert baseline.boll_upper is not None
    assert baseline.previous_10d_high is not None
    assert baseline.atr14 is not None

    reversal_price = max(
        110.5 + 1.5 * (665 / 20) ** 0.5,
        baseline.previous_10d_high + 0.25 * baseline.atr14 + 0.01,
    )
    reversal = calculate_historical_setup(bars, current_price=reversal_price)

    assert reversal.has_reversal_trend == "是"
    assert reversal.is_suitable_for_entry == "否"


def test_calculate_historical_setup_returns_all_none_with_nineteen_days():
    result = calculate_historical_setup(_daily_bars([100.0] * 19), current_price=100)

    assert all(value is None for value in vars(result).values())


@pytest.mark.parametrize("history_size", [20, 24])
def test_calculate_historical_setup_returns_z_score_before_direction_history_is_available(
    history_size,
):
    result = calculate_historical_setup(
        _daily_bars([float(value) for value in range(1, history_size + 1)]),
        current_price=30,
    )

    assert result.z_score is not None
    assert result.boll_mid is not None
    assert result.ma20_direction is None
    assert result.has_reversal_trend is None
    assert result.is_suitable_for_entry is None
