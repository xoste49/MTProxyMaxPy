from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from mtproxymaxpy import systemd
from mtproxymaxpy.config import migration


def test_migration_parse_bool_and_settings_fallback(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        migration._parse_bool("maybe")

    cfg = tmp_path / "settings.conf"
    cfg.write_text("INVALID LINE\nPROXY_PORT='abc'\n", encoding="utf-8")
    parsed = migration._parse_settings_conf(cfg)
    assert parsed["proxy_port"] == "abc"


def test_migration_parse_bad_rows_and_instances(tmp_path: Path) -> None:
    sec = tmp_path / "secrets.conf"
    sec.write_text("alice|" + "a" * 32 + "|0|true|bad|0|0||\n", encoding="utf-8")
    assert migration._parse_secrets_conf(sec) == []

    up = tmp_path / "upstreams.conf"
    up.write_text("#comment\nwarp|socks5|127.0.0.1:1080|||100|eth0|maybe\n", encoding="utf-8")
    assert migration._parse_upstreams_conf(up) == []

    inst = tmp_path / "instances.conf"
    inst.write_text("#comment\nmain|443|true|ok\nbad|x|true|bad\n", encoding="utf-8")
    items = migration._parse_instances_conf(inst)
    assert len(items) == 1
    assert items[0].name == "main"


def test_run_migration_detect_none_and_error_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "s.conf"
    src.write_text("PROXY_PORT='443'\n", encoding="utf-8")

    monkeypatch.setattr(migration, "detect_legacy", lambda: {"settings": src, "secrets": src, "upstreams": src, "instances": src})

    monkeypatch.setattr(
        "mtproxymaxpy.config.settings.save_settings",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("save settings")),
    )
    monkeypatch.setattr("mtproxymaxpy.config.secrets.save_secrets", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("save secrets")))
    monkeypatch.setattr("mtproxymaxpy.config.upstreams.save_upstreams", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("save ups")))
    monkeypatch.setattr("mtproxymaxpy.config.instances.save_instances", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("save inst")))

    res = migration.run_migration(files=None)
    assert any(e.startswith("settings:") for e in res.errors)
    assert any(e.startswith("secrets:") for e in res.errors)
    assert any(e.startswith("upstreams:") for e in res.errors)
    assert any(e.startswith("instances:") for e in res.errors)


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
