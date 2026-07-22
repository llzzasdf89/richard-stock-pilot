from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class IntradayBar:
    time: datetime
    close: float


class LongbridgeService:
    """Longbridge access seam.

    The first implementation returns deterministic data so the app is usable
    without credentials. Replacing these methods with real SDK calls will not
    change controller or view contracts.
    """

    def get_intraday_bars(self, symbol: str, interval: str = "5m", limit: int = 30) -> list[IntradayBar]:
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        base = 100.0
        if symbol.endswith(".US"):
            base = 200.0
        if symbol.endswith(".HK"):
            base = 360.0

        bars: list[IntradayBar] = []
        for index in range(limit):
            close = base + index * 0.2
            if index == limit - 1:
                close = base + 8.0
            bars.append(IntradayBar(time=now - timedelta(minutes=(limit - index) * 5), close=close))
        return bars
