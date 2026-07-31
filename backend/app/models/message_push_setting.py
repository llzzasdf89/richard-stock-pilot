from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MessagePushSetting(Base):
    __tablename__ = "message_push_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    min_market_cap: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    min_avg_volume: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
