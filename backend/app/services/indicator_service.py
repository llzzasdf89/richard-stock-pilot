from __future__ import annotations

from math import sqrt


Band = dict[str, float | None]


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
