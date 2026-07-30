from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]


def load_environment(repo_root: Path | None = None) -> None:
    root = repo_root or REPO_ROOT
    load_dotenv(root / ".env", override=False)


def resolve_database_url(database_url: str, backend_root: Path = BACKEND_ROOT) -> str:
    sqlite_prefix = "sqlite:///"
    if not database_url.startswith(sqlite_prefix):
        return database_url

    path_text = database_url.removeprefix(sqlite_prefix)
    database_path = Path(path_text)
    if database_path.is_absolute():
        return database_url
    return f"{sqlite_prefix}{backend_root / database_path}"


load_environment()

DATABASE_URL = resolve_database_url(os.getenv("DATABASE_URL", "sqlite:///./richard_stock_pilot.db"))


def message_push_enabled() -> bool:
    return os.getenv("ENABLE_MESSAGE_PUSH", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
