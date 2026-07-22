from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]


def load_environment(repo_root: Path | None = None, backend_root: Path | None = None) -> None:
    root = repo_root or REPO_ROOT
    backend = backend_root or BACKEND_ROOT
    load_dotenv(root / ".env", override=False)
    load_dotenv(backend / ".env", override=False)


load_environment()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./richard_stock_pilot.db")
