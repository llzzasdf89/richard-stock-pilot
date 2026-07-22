from app.services.indicator_service import (
    calculate_bollinger,
    calculate_break_percent,
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
