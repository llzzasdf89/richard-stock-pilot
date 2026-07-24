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


def get_db() -> Generator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
