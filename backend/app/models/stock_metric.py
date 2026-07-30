from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class StockMetricDaily(Base):
    __tablename__ = "stock_metrics_daily"
    __table_args__ = (
        UniqueConstraint("stock_id", "trade_date", "boll_period", "boll_std_multiplier"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    close: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    market_cap: Mapped[Decimal] = mapped_column(Numeric, nullable=False, index=True)
    avg_volume_1m: Mapped[Decimal] = mapped_column(Numeric, nullable=False, index=True)
    boll_period: Mapped[int] = mapped_column(Integer, nullable=False)
    boll_std_multiplier: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    boll_mid: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    boll_upper: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    boll_lower: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    prev_close: Mapped[Decimal | None] = mapped_column(Numeric)
    prev_boll_upper: Mapped[Decimal | None] = mapped_column(Numeric)
    prev_boll_lower: Mapped[Decimal | None] = mapped_column(Numeric)
    signal_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    break_percent: Mapped[Decimal | None] = mapped_column(Numeric)
    ma20_direction: Mapped[str | None] = mapped_column(String)
    z_score: Mapped[Decimal | None] = mapped_column(Numeric)
    atr14: Mapped[Decimal | None] = mapped_column(Numeric)
    previous_10d_low: Mapped[Decimal | None] = mapped_column(Numeric)
    previous_10d_high: Mapped[Decimal | None] = mapped_column(Numeric)
    has_reversal_trend: Mapped[str | None] = mapped_column(String)
    is_suitable_for_entry: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    stock = relationship("Stock", back_populates="daily_metrics")
