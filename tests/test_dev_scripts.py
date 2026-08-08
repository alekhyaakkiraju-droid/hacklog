"""Tests for local developer run/stop scripts (WO-039)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"


@pytest.fixture
def run_sh() -> str:
    return (SCRIPTS / "run.sh").read_text(encoding="utf-8")


@pytest.fixture
def stop_sh() -> str:
    return (SCRIPTS / "stop.sh").read_text(encoding="utf-8")


def test_run_sh_has_correct_shebang() -> None:
    first_line = (SCRIPTS / "run.sh").read_text(encoding="utf-8").splitlines()[0]
    assert first_line == "#!/bin/sh"


def test_stop_sh_has_correct_shebang() -> None:
    first_line = (SCRIPTS / "stop.sh").read_text(encoding="utf-8").splitlines()[0]
    assert first_line == "#!/bin/sh"


def test_stop_sh_uses_sigterm_not_kill_dash_nine(stop_sh: str) -> None:
    assert "kill -TERM" in stop_sh or "kill -15" in stop_sh
    assert "kill -9" not in stop_sh
    assert "kill -KILL" not in stop_sh


def test_run_sh_loads_env_and_configmanager(run_sh: str) -> None:
    assert ".env" in run_sh
    assert "HACKLOG_SMTP_USER" in run_sh
    assert "ConfigManager" in run_sh
    assert "conf/server.conf" in run_sh or "HACKLOG_CONFIG" in run_sh


def test_makefile_exposes_dev_targets() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    for target in ("dev-start", "dev-stop", "dev-status", "dev-restart"):
        assert f"{target}:" in makefile


def test_scripts_are_executable() -> None:
    for name in ("run.sh", "stop.sh", "dev-status.sh"):
        path = SCRIPTS / name
        assert path.exists(), f"missing {name}"
        assert path.stat().st_mode & 0o111, f"{name} should be executable"


def test_stop_sh_exits_cleanly_when_not_running(tmp_path: Path) -> None:
    pidfile = tmp_path / "hacklog.pid"
    script = SCRIPTS / "stop.sh"
    env = {"HACKLOG_PIDFILE": str(pidfile)}
    import os
    import subprocess

    result = subprocess.run(
        [str(script)],
        cwd=REPO_ROOT,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "not running" in result.stdout.lower()
