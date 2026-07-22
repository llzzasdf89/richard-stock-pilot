from __future__ import annotations

import os

from app.config import load_environment


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
