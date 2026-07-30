from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import DATABASE_URL
import app.models  # noqa: F401
from app.models.base import Base


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db(target_engine: Engine | None = None) -> None:
    active_engine = target_engine or engine
    Base.metadata.create_all(active_engine)
    _ensure_schema(active_engine)


def _ensure_schema(active_engine: Engine) -> None:
    inspector = inspect(active_engine)
    if "stocks" not in inspector.get_table_names():
        return
    stock_columns = {column["name"] for column in inspector.get_columns("stocks")}
    if "earnings_date" not in stock_columns:
        with active_engine.begin() as connection:
            connection.execute(text("ALTER TABLE stocks ADD COLUMN earnings_date DATE"))

    if "stock_metrics_daily" not in inspector.get_table_names():
        return
    metric_columns = {
        column["name"] for column in inspect(active_engine).get_columns("stock_metrics_daily")
    }
    additions = {
        "ma20_direction": "VARCHAR",
        "z_score": "NUMERIC",
        "atr14": "NUMERIC",
        "previous_10d_low": "NUMERIC",
        "previous_10d_high": "NUMERIC",
        "has_reversal_trend": "VARCHAR",
        "is_suitable_for_entry": "VARCHAR",
    }
    with active_engine.begin() as connection:
        for column_name, column_type in additions.items():
            if column_name not in metric_columns:
                connection.execute(
                    text(
                        f"ALTER TABLE stock_metrics_daily "
                        f"ADD COLUMN {column_name} {column_type}"
                    )
                )


def get_db() -> Generator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
