from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_start_script_stops_when_daily_sync_fails(tmp_path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    command_log = tmp_path / "commands.log"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_uv = fake_bin / "uv"
    fake_npm = fake_bin / "npm"
    fake_uv.write_text(
        """#!/usr/bin/env bash
echo "uv $*" >> "${START_SCRIPT_TEST_LOG}"
if [[ "$*" == "run python -m app.scripts.has_daily_screening_data" ]]; then
  exit 1
fi
if [[ "$*" == run\\ python\\ -m\\ app.scripts.sync_daily_screening* ]]; then
  exit 42
fi
if [[ "$*" == run\\ uvicorn* ]]; then
  echo "backend-started" >> "${START_SCRIPT_TEST_LOG}"
fi
exit 0
""",
        encoding="utf-8",
    )
    fake_npm.write_text(
        """#!/usr/bin/env bash
echo "npm $*" >> "${START_SCRIPT_TEST_LOG}"
if [[ "$*" == run\\ dev* ]]; then
  echo "frontend-started" >> "${START_SCRIPT_TEST_LOG}"
fi
exit 0
""",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    fake_npm.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["START_SCRIPT_TEST_LOG"] = str(command_log)
    env["DAILY_SYNC_SYMBOLS"] = "AAPL.US"

    result = subprocess.run(
        [str(repo_root / "start.sh")],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    log = command_log.read_text(encoding="utf-8")
    assert result.returncode != 0
    assert "日线批处理同步失败，停止启动程序。" in result.stderr
    assert "backend-started" not in log
    assert "frontend-started" not in log
