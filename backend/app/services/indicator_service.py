from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import isclose, sqrt


Band = dict[str, float | None]


@dataclass(frozen=True)
class DailyPriceBar:
    trade_date: date
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class HistoricalSetup:
    ma20_direction: str | None
    z_score: float | None
    atr14: float | None
    previous_10d_low: float | None
    previous_10d_high: float | None
    boll_mid: float | None
    boll_upper: float | None
    boll_lower: float | None
    has_reversal_trend: str | None
    is_suitable_for_entry: str | None


def calculate_bollinger(
    values: list[float],
    period: int = 20,
    std_multiplier: float = 2,
) -> list[Band]:
    if period <= 0:
        raise ValueError("period must be positive")

    bands: list[Band] = []
    for index in range(len(values)):
        if index + 1 < period:
            bands.append({"mid": None, "upper": None, "lower": None})
            continue

        window = values[index + 1 - period : index + 1]
        mid = sum(window) / period
        variance = sum((value - mid) ** 2 for value in window) / period
        std = sqrt(variance)
        bands.append(
            {
                "mid": mid,
                "upper": mid + std_multiplier * std,
                "lower": mid - std_multiplier * std,
            }
        )

    return bands


def detect_boll_signal(
    prev_close: float,
    close: float,
    prev_upper: float,
    upper: float,
    prev_lower: float,
    lower: float,
) -> str:
    if prev_close <= prev_upper and close > upper:
        return "upper_breakout"
    if prev_close >= prev_lower and close < lower:
        return "lower_breakdown"
    return "none"


def calculate_break_percent(
    signal_type: str,
    close: float,
    upper: float,
    lower: float,
) -> float | None:
    if signal_type == "upper_breakout":
        return (close - upper) / upper
    if signal_type == "lower_breakdown":
        return (lower - close) / lower
    return None


def calculate_true_range(high: float, low: float, previous_close: float) -> float:
    return max(
        high - low,
        abs(high - previous_close),
        abs(low - previous_close),
    )


def calculate_historical_setup(
    bars: list[DailyPriceBar],
    current_price: float,
    boll_period: int = 20,
    boll_std_multiplier: float = 2,
) -> HistoricalSetup:
    normalized_by_date = {
        bar.trade_date: bar
        for bar in sorted(bars, key=lambda item: item.trade_date)
    }
    normalized = list(normalized_by_date.values())
    minimum_history = max(25, boll_period + 5, 15)
    if len(normalized) < minimum_history:
        return _empty_historical_setup()

    closes = [bar.close for bar in normalized]
    current_ma20 = sum(closes[-20:]) / 20
    variance = sum((close - current_ma20) ** 2 for close in closes[-20:]) / 20
    sd20 = sqrt(variance)
    z_score = 0.0 if sd20 == 0 else (current_price - current_ma20) / sd20
    comparison_ma20 = sum(closes[-25:-5]) / 20
    ma_delta = current_ma20 - comparison_ma20
    if ma_delta > 0:
        ma20_direction = "上升"
    elif ma_delta < 0:
        ma20_direction = "下降"
    else:
        ma20_direction = "需人工判断"

    current_band = calculate_bollinger(
        closes[-boll_period:],
        period=boll_period,
        std_multiplier=boll_std_multiplier,
    )[-1]
    if None in (current_band["mid"], current_band["upper"], current_band["lower"]):
        return _empty_historical_setup()

    atr_bars = normalized[-14:]
    previous_close = normalized[-15].close
    true_ranges: list[float] = []
    for bar in atr_bars:
        true_ranges.append(calculate_true_range(bar.high, bar.low, previous_close))
        previous_close = bar.close
    atr14 = sum(true_ranges) / 14
    previous_10d_low = min(bar.low for bar in normalized[-10:])
    previous_10d_high = max(bar.high for bar in normalized[-10:])
    boll_mid = float(current_band["mid"])
    boll_upper = float(current_band["upper"])
    boll_lower = float(current_band["lower"])

    long_z_extreme = z_score < -1.5 or isclose(z_score, -1.5)
    short_z_extreme = z_score > 1.5 or isclose(z_score, 1.5)
    long_reversal = (
        ma20_direction == "上升"
        and long_z_extreme
        and current_price < previous_10d_low - 0.25 * atr14
    )
    short_reversal = (
        ma20_direction == "下降"
        and short_z_extreme
        and current_price > previous_10d_high + 0.25 * atr14
    )
    has_reversal_trend = "是" if long_reversal or short_reversal else "否"
    suitable_long = (
        ma20_direction == "上升"
        and long_z_extreme
        and has_reversal_trend == "否"
    )
    suitable_short = (
        ma20_direction == "下降"
        and short_z_extreme
        and has_reversal_trend == "否"
    )
    return HistoricalSetup(
        ma20_direction=ma20_direction,
        z_score=z_score,
        atr14=atr14,
        previous_10d_low=previous_10d_low,
        previous_10d_high=previous_10d_high,
        boll_mid=boll_mid,
        boll_upper=boll_upper,
        boll_lower=boll_lower,
        has_reversal_trend=has_reversal_trend,
        is_suitable_for_entry="是" if suitable_long or suitable_short else "否",
    )


def _empty_historical_setup() -> HistoricalSetup:
    return HistoricalSetup(
        ma20_direction=None,
        z_score=None,
        atr14=None,
        previous_10d_low=None,
        previous_10d_high=None,
        boll_mid=None,
        boll_upper=None,
        boll_lower=None,
        has_reversal_trend=None,
        is_suitable_for_entry=None,
    )
