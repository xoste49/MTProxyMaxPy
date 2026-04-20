from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from mtproxymaxpy import doctor, systemd


class _CtxSocket:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_check_binary_present_with_version(monkeypatch: pytest.MonkeyPatch) -> None:
    import mtproxymaxpy.constants as c

    class _FakePath:
        def exists(self):
            return True

        def stat(self):
            return SimpleNamespace(st_mode=0o755)

        def __str__(self):
            return "/fake/telemt"

    monkeypatch.setattr(c, "BINARY_PATH", _FakePath())
    monkeypatch.setattr(
        doctor.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout="telemt 1.2.3\n", stderr=""),
    )

    out = doctor.check_binary()
    assert out["ok"] is True
    assert out["version"] == "1.2.3"


def test_check_binary_not_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    import mtproxymaxpy.constants as c

    class _FakePath:
        def exists(self):
            return True

        def stat(self):
            return SimpleNamespace(st_mode=0o644)

        def __str__(self):
            return "/fake/telemt"

    monkeypatch.setattr(c, "BINARY_PATH", _FakePath())
    out = doctor.check_binary()
    assert out["ok"] is False
    assert out["version"] is None


def test_check_process(monkeypatch: pytest.MonkeyPatch) -> None:
    import mtproxymaxpy as pkg

    mod = SimpleNamespace(is_running=lambda: True, get_pid=lambda: 42)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.process_manager", mod)
    monkeypatch.setattr(pkg, "process_manager", mod, raising=False)
    out = doctor.check_process()
    assert out == {"ok": True, "running": True, "pid": 42}


def test_check_port_listening_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda x: "yes" if x == "ss" else None)
    monkeypatch.setattr(
        doctor.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout="LISTEN 0 128 0.0.0.0:443", stderr=""),
    )
    assert doctor.check_port_listening(443) == {"ok": True, "tool": "ss"}

    calls = {"n": 0}

    def _which(name: str):
        return "yes" if name == "netstat" else None

    def _run(*a, **k):
        calls["n"] += 1
        return SimpleNamespace(stdout="tcp 0 0 0.0.0.0:8443 LISTEN", stderr="")

    monkeypatch.setattr(doctor.shutil, "which", _which)
    monkeypatch.setattr(doctor.subprocess, "run", _run)
    assert doctor.check_port_listening(8443) == {"ok": True, "tool": "netstat"}
    assert calls["n"] == 1

    monkeypatch.setattr(doctor.shutil, "which", lambda _: None)
    monkeypatch.setattr(doctor.socket, "create_connection", lambda *a, **k: _CtxSocket())
    assert doctor.check_port_listening(80) == {"ok": True, "tool": "socket"}

    def _raise_conn(*a, **k):
        raise OSError("no")

    monkeypatch.setattr(doctor.socket, "create_connection", _raise_conn)
    out = doctor.check_port_listening(81)
    assert out["ok"] is False
    assert out["tool"] == "socket"


def test_check_tls_handshake_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda _: None)
    assert doctor.check_tls_handshake("127.0.0.1", 443)["ok"] is None

    monkeypatch.setattr(doctor.shutil, "which", lambda _: "openssl")
    monkeypatch.setattr(
        doctor.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=b"Protocol : TLSv1.3", stderr=b""),
    )
    ok = doctor.check_tls_handshake("127.0.0.1", 443, "example.com")
    assert ok["ok"] is True

    def _timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="openssl", timeout=1)

    monkeypatch.setattr(doctor.subprocess, "run", _timeout)
    assert doctor.check_tls_handshake("127.0.0.1", 443)["note"] == "timeout"


def test_check_secrets_and_disk_and_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    sec_mod = SimpleNamespace(
        load_secrets=lambda: [
            SimpleNamespace(label="a", expires="1900-01-01", enabled=True),
            SimpleNamespace(label="b", expires=None, enabled=False),
        ],
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.config.secrets", sec_mod)
    out = doctor.check_secrets()
    assert out["ok"] is True
    assert out["enabled"] == 1
    assert "a" in out["expired"]

    import mtproxymaxpy.constants as c

    monkeypatch.setattr(c, "INSTALL_DIR", Path(tempfile.gettempdir()) / "not-real")
    monkeypatch.setattr(
        doctor.shutil,
        "disk_usage",
        lambda p: SimpleNamespace(total=0, used=0, free=600 * 1024 * 1024),
    )
    disk = doctor.check_disk_space(min_mb=500)
    assert disk["ok"] is True

    import mtproxymaxpy as pkg

    met_mod = SimpleNamespace(get_stats=lambda: {"available": False, "error": "x"})
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.metrics", met_mod)
    monkeypatch.setattr(pkg, "metrics", met_mod, raising=False)
    assert doctor.check_metrics_endpoint() == {"ok": False, "error": "x"}


def test_check_telegram_service_and_full_doctor(monkeypatch: pytest.MonkeyPatch) -> None:
    import mtproxymaxpy.constants as c

    monkeypatch.setattr(c, "SYSTEMD_TELEGRAM_SERVICE", "mtproxymaxpy-telegram")
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(load_settings=lambda: SimpleNamespace(telegram_enabled=False)),
    )
    assert doctor.check_telegram_service() == {"ok": True, "note": "disabled"}

    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(load_settings=lambda: SimpleNamespace(telegram_enabled=True)),
    )
    monkeypatch.setattr(doctor.shutil, "which", lambda x: "systemctl" if x == "systemctl" else None)
    import mtproxymaxpy as pkg

    sd_mod = SimpleNamespace(is_active=lambda name: True)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.systemd", sd_mod)
    monkeypatch.setattr(pkg, "systemd", sd_mod, raising=False)
    tg = doctor.check_telegram_service()
    assert tg["ok"] is True

    monkeypatch.setattr(doctor.shutil, "which", lambda _: None)
    assert doctor.check_telegram_service()["ok"] is None

    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(load_settings=lambda: SimpleNamespace(proxy_port=443, proxy_domain="example.com")),
    )
    monkeypatch.setattr(doctor, "check_binary", lambda: {"ok": True})
    monkeypatch.setattr(doctor, "check_process", lambda: {"ok": True})
    monkeypatch.setattr(doctor, "check_port_listening", lambda port: {"ok": True, "port": port})
    monkeypatch.setattr(doctor, "check_tls_handshake", lambda host, port, domain="": {"ok": True})
    monkeypatch.setattr(doctor, "check_secrets", lambda: {"ok": True})
    monkeypatch.setattr(doctor, "check_disk_space", lambda: {"ok": True})
    monkeypatch.setattr(doctor, "check_metrics_endpoint", lambda: {"ok": True})
    monkeypatch.setattr(doctor, "check_telegram_service", lambda: {"ok": True})
    monkeypatch.setattr(doctor, "check_middle_proxy_compat", lambda: {"ok": True})
    res = doctor.run_full_doctor()
    assert [r["name"] for r in res] == [
        "Binary present",
        "Process running",
        "Port listening",
        "TLS handshake",
        "Secrets configured",
        "Disk space",
        "Metrics endpoint",
        "Telegram service",
        "Middle proxy compat",
    ]


def test_systemd_unit_templates_and_control(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    proxy_unit = systemd._proxy_unit("/usr/bin/python3")
    assert "ExecStart=/usr/bin/python3 -m mtproxymaxpy start --no-tui" in proxy_unit
    tg_unit = systemd._telegram_unit("/usr/bin/python3")
    assert "telegram-bot --no-tui" in tg_unit

    monkeypatch.setattr(systemd, "SYSTEMD_UNIT_DIR", tmp_path)
    monkeypatch.setattr(systemd, "_python_exe", lambda: "/python")
    calls: list[tuple] = []

    def _ok(*args, check=True):
        calls.append((args, check))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(systemd, "_systemctl", _ok)
    systemd.install(telegram=True)
    assert (tmp_path / f"{systemd.SYSTEMD_SERVICE}.service").exists()
    assert (tmp_path / f"{systemd.SYSTEMD_TELEGRAM_SERVICE}.service").exists()
    assert any(c[0] == ("daemon-reload",) for c in calls)

    systemd.uninstall(telegram=True)
    assert not (tmp_path / f"{systemd.SYSTEMD_SERVICE}.service").exists()

    monkeypatch.setattr(systemd, "_systemctl", lambda *a, **k: SimpleNamespace(returncode=0))
    assert systemd.is_active() is True
    assert systemd.is_enabled() is True


def test_systemctl_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    def _missing(*a, **k):
        raise FileNotFoundError("no systemctl")

    monkeypatch.setattr(systemd.subprocess, "run", _missing)
    with pytest.raises(RuntimeError, match="systemctl not found"):
        systemd._systemctl("status")

    def _bad(*a, **k):
        raise subprocess.CalledProcessError(5, ["systemctl"], stderr=b"fail")

    monkeypatch.setattr(systemd.subprocess, "run", _bad)
    with pytest.raises(RuntimeError, match="failed"):
        systemd._systemctl("start", "x")
