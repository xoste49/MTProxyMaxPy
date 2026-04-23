from __future__ import annotations

import subprocess
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from mtproxymaxpy import systemd

if TYPE_CHECKING:
    from pathlib import Path


def test_systemd_remaining_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(systemd, "SYSTEMD_UNIT_DIR", tmp_path / "missing")
    with pytest.raises(RuntimeError, match="unit directory not found"):
        systemd.install_telegram_service()

    monkeypatch.setattr(systemd, "SYSTEMD_UNIT_DIR", tmp_path)
    monkeypatch.setattr(systemd, "_python_exe", lambda: "/python")

    calls: list[tuple] = []

    def _ctl(*args, check=True):
        calls.append((args, check))
        if args == ("start", systemd.SYSTEMD_SERVICE):
            raise RuntimeError("start failed")
        if args == ("start", systemd.SYSTEMD_TELEGRAM_SERVICE):
            raise RuntimeError("start failed")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(systemd, "_systemctl", _ctl)
    systemd.install(telegram=True)
    assert any(c[0] == ("enable", systemd.SYSTEMD_SERVICE) for c in calls)

    calls.clear()
    systemd.install_telegram_service()
    assert any(c[0] == ("enable", systemd.SYSTEMD_TELEGRAM_SERVICE) for c in calls)

    # wrappers + false return branches
    monkeypatch.setattr(systemd, "_systemctl", lambda *a, **k: SimpleNamespace(returncode=1))
    systemd.start_service("svc")
    systemd.stop_service("svc")
    systemd.restart_service("svc")
    assert systemd.is_active("svc") is False
    assert systemd.is_enabled("svc") is False


def test_systemd_python_exe_and_systemctl_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(systemd.sys, "executable", "/bin/python3")
    assert systemd._python_exe() == "/bin/python3"

    monkeypatch.setattr(systemd.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stderr=b""))
    out = systemd._systemctl("status", check=False)
    assert out.returncode == 0

    def _bad(*a, **k):
        raise subprocess.CalledProcessError(1, ["systemctl"], stderr=b"")

    monkeypatch.setattr(systemd.subprocess, "run", _bad)
    with pytest.raises(RuntimeError, match="failed"):
        systemd._systemctl("start", "x")
