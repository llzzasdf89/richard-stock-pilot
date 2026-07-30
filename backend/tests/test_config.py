from __future__ import annotations

import os

from sqlalchemy import create_engine, inspect, text

from app.config import load_environment
from app.config import message_push_enabled
from app.config import resolve_database_url
from app.db import init_db


def test_load_environment_reads_root_env_file(monkeypatch, tmp_path) -> None:
    repo_root = tmp_path / "repo"
    backend_root = repo_root / "backend"
    backend_root.mkdir(parents=True)
    (repo_root / ".env").write_text(
        "DATABASE_URL=sqlite:///root.db\nLONGBRIDGE_REGION=cn\nLONGBRIDGE_APP_KEY=test-key\n",
        encoding="utf-8",
    )
    (backend_root / ".env").write_text(
        "LONGBRIDGE_APP_KEY=backend-key\nBACKEND_ONLY_SETTING=unused\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("LONGBRIDGE_REGION", raising=False)
    monkeypatch.delenv("LONGBRIDGE_APP_KEY", raising=False)
    monkeypatch.delenv("BACKEND_ONLY_SETTING", raising=False)

    load_environment(repo_root=repo_root)

    assert os.environ["DATABASE_URL"] == "sqlite:///root.db"
    assert os.environ["LONGBRIDGE_REGION"] == "cn"
    assert os.environ["LONGBRIDGE_APP_KEY"] == "test-key"
    assert "BACKEND_ONLY_SETTING" not in os.environ


def test_load_environment_keeps_existing_environment_values(monkeypatch, tmp_path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)
    (repo_root / ".env").write_text("LONGBRIDGE_REGION=cn\n", encoding="utf-8")

    monkeypatch.setenv("LONGBRIDGE_REGION", "hk")

    load_environment(repo_root=repo_root)

    assert os.environ["LONGBRIDGE_REGION"] == "hk"


def test_resolve_database_url_anchors_relative_sqlite_paths_to_backend_root(tmp_path) -> None:
    backend_root = tmp_path / "backend"
    backend_root.mkdir()

    url = resolve_database_url("sqlite:///./richard_stock_pilot.db", backend_root=backend_root)

    assert url == f"sqlite:///{backend_root / 'richard_stock_pilot.db'}"


def test_message_push_enabled_defaults_to_false_and_accepts_common_true_values(monkeypatch) -> None:
    monkeypatch.delenv("ENABLE_MESSAGE_PUSH", raising=False)
    assert message_push_enabled() is False

    for value in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("ENABLE_MESSAGE_PUSH", value)
        assert message_push_enabled() is True


def test_init_db_adds_technical_indicator_columns_to_existing_metric_table() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE stocks (id INTEGER PRIMARY KEY)"))
        connection.execute(
            text(
                """
                CREATE TABLE stock_metrics_daily (
                    id INTEGER PRIMARY KEY,
                    stock_id INTEGER NOT NULL,
                    trade_date DATE NOT NULL
                )
                """
            )
        )

    init_db(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("stock_metrics_daily")}
    assert {
        "ma20_direction",
        "atr14",
        "previous_10d_low",
        "previous_10d_high",
        "has_reversal_trend",
        "is_suitable_for_entry",
    } <= columns
