from __future__ import annotations

import io
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from mtproxymaxpy import process_manager as pm


def test_to_rfc3339_expiration() -> None:
    assert pm._to_rfc3339_expiration("") is None
    assert pm._to_rfc3339_expiration("0") is None
    assert pm._to_rfc3339_expiration("2026-01-02") == "2026-01-02T23:59:59Z"
    assert pm._to_rfc3339_expiration("2026-01-02T03:04:05") == "2026-01-02T03:04:05Z"
    assert pm._to_rfc3339_expiration("2026-01-02T03:04:05Z") == "2026-01-02T03:04:05Z"
    assert pm._to_rfc3339_expiration("not-a-date") is None


def test_build_toml_config_contains_expected_sections() -> None:
    settings = SimpleNamespace(
        ad_tag="TAG",
        masking_enabled=True,
        proxy_port=443,
        proxy_protocol=True,
        proxy_protocol_trusted_cidrs="10.0.0.0/8, 192.168.0.0/16",
        proxy_metrics_port=9090,
        proxy_domain="cloudflare.com",
        unknown_sni_action="mask",
        masking_port=8443,
        masking_host="example.com",
        fake_cert_len=1024,
    )
    sec1 = SimpleNamespace(label="u1", key="a" * 32, enabled=True, max_conns=10, max_ips=2, quota_bytes=123, expires="2026-12-31")
    sec2 = SimpleNamespace(label="u2", key="b" * 32, enabled=False, max_conns=0, max_ips=0, quota_bytes=0, expires="")
    up1 = SimpleNamespace(enabled=True, type="socks5", weight=10, addr="127.0.0.1:1080", user="user", password="pass", iface="")
    up2 = SimpleNamespace(enabled=True, type="direct", weight=10, addr="", user="", password="", iface="")

    text = pm._build_toml_config(settings, [sec1, sec2], [up1, up2], "")
    assert "[general]" in text
    assert "[access.users]" in text
    assert '"u1" = "' in text
    assert "[access.user_max_tcp_conns]" in text
    assert "[[upstreams]]" in text
    assert "proxy_protocol = true" in text
    assert 'proxy_protocol_trusted_cidrs = ["10.0.0.0/8", "192.168.0.0/16"]' in text


def test_write_toml_config_and_atomic_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg_dir = tmp_path / "mtproxy"
    stats_dir = tmp_path / "relay_stats"
    target = cfg_dir / "config.toml"
    monkeypatch.setattr(pm, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(pm, "STATS_DIR", stats_dir)
    monkeypatch.setattr(pm, "TOML_CONFIG_FILE", target)
    monkeypatch.setattr(pm, "_build_toml_config", lambda *a, **k: "x=1\n")
    monkeypatch.setattr(pm, "load_settings", lambda: object())
    monkeypatch.setattr(pm, "load_secrets", list)
    monkeypatch.setattr(pm, "load_upstreams", list)

    pm.write_toml_config()
    assert target.read_text(encoding="utf-8") == "x=1\n"

    def _boom(src, dst):
        raise RuntimeError("replace failed")

    monkeypatch.setattr(pm.os, "replace", _boom)
    with pytest.raises(RuntimeError, match="replace failed"):
        pm.write_toml_config()


def test_download_url_and_latest_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pm, "_detect_arch", lambda: "x86_64")
    monkeypatch.setattr(pm, "TELEMT_DOWNLOAD_URL_TEMPLATE", "https://x/{version}/{arch}")
    assert pm._resolve_download_url("1.2.3") == "https://x/1.2.3/x86_64"

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"tag_name": "v9.9.9"}

    monkeypatch.setattr(pm.httpx, "get", lambda *a, **k: _Resp())
    assert pm.get_latest_version() == "9.9.9"

    monkeypatch.setattr(pm.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert pm.get_latest_version() == pm.TELEMT_VERSION


def test_get_binary_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pm, "is_binary_present", lambda: True)

    monkeypatch.setattr(
        pm.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout="telemt 3.4.0\n", stderr=""),
    )
    assert pm.get_binary_version(default="1.0.0") == "3.4.0"

    monkeypatch.setattr(
        pm.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout="version: unknown\n", stderr=""),
    )
    assert pm.get_binary_version(default="1.0.0") == "1.0.0"

    monkeypatch.setattr(pm, "is_binary_present", lambda: False)
    assert pm.get_binary_version(default="2.0.0") == "2.0.0"


def test_binary_presence_and_download(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    binary = bin_dir / "telemt"
    monkeypatch.setattr(pm, "BINARY_DIR", bin_dir)
    monkeypatch.setattr(pm, "BINARY_PATH", binary)
    monkeypatch.setattr(pm, "BINARY_NAME", "telemt")
    monkeypatch.setattr(pm, "_resolve_download_url", lambda version: "https://example")

    monkeypatch.setattr(pm, "is_binary_present", lambda: True)
    pm.download_binary(force=False)

    monkeypatch.setattr(pm, "is_binary_present", lambda: False)
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w:gz") as tf:
        payload = b"#!/bin/sh\necho ok\n"
        ti = tarfile.TarInfo("telemt")
        ti.size = len(payload)
        tf.addfile(ti, io.BytesIO(payload))
    tar_data = tar_buf.getvalue()

    class _Stream:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def raise_for_status(self):
            return None

        def iter_bytes(self, chunk_size=65536):
            yield tar_data

    monkeypatch.setattr(pm.httpx, "stream", lambda *a, **k: _Stream())
    pm.download_binary(force=True)
    assert binary.exists()


def test_download_binary_cleanup_on_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setattr(pm, "BINARY_DIR", bin_dir)
    monkeypatch.setattr(pm, "BINARY_PATH", bin_dir / "telemt")
    monkeypatch.setattr(pm, "BINARY_NAME", "telemt")
    monkeypatch.setattr(pm, "is_binary_present", lambda: False)
    monkeypatch.setattr(pm, "_resolve_download_url", lambda version: "https://example")

    class _Stream:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def raise_for_status(self):
            return None

        def iter_bytes(self, chunk_size=65536):
            yield b"not a tar"

    monkeypatch.setattr(pm.httpx, "stream", lambda *a, **k: _Stream())
    with pytest.raises(tarfile.ReadError):
        pm.download_binary(force=True)
    assert not (bin_dir / "telemt.tmp").exists()


def test_pid_and_running_helpers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pid_file = tmp_path / "telemt.pid"
    monkeypatch.setattr(pm, "PID_FILE", pid_file)

    assert pm._read_pid() is None
    pm._write_pid(123)
    assert pm._read_pid() == 123
    pm._clear_pid()
    assert pm._read_pid() is None

    pm._write_pid(99)
    monkeypatch.setattr(pm.os, "kill", lambda pid, sig: None)
    assert pm.is_running() is True

    def _dead(pid, sig):
        raise ProcessLookupError

    monkeypatch.setattr(pm.os, "kill", _dead)
    assert pm.is_running() is False
    monkeypatch.setattr(pm, "is_running", lambda: False)
    assert pm.get_pid() is None


def test_start_stop_restart_reload_and_status(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    pid_file = tmp_path / "telemt.pid"
    binary = tmp_path / "telemt"
    binary.write_text("x", encoding="utf-8")
    cfg = tmp_path / "config.toml"
    cfg.write_text("x=1\n", encoding="utf-8")

    monkeypatch.setattr(pm, "INSTALL_DIR", install_dir)
    monkeypatch.setattr(pm, "PID_FILE", pid_file)
    monkeypatch.setattr(pm, "BINARY_PATH", binary)
    monkeypatch.setattr(pm, "TOML_CONFIG_FILE", cfg)
    monkeypatch.setattr(pm, "is_binary_present", lambda: True)
    monkeypatch.setattr(pm, "write_toml_config", lambda public_ip="": None)
    monkeypatch.setattr(pm.time, "sleep", lambda _: None)

    class _Proc:
        pid = 321
        returncode = 0

        def poll(self):
            return None

    monkeypatch.setattr(pm.subprocess, "Popen", lambda *a, **k: _Proc())
    monkeypatch.setattr(pm, "is_running", lambda: False)
    pid = pm.start(public_ip="1.1.1.1")
    assert pid == 321
    assert pm._read_pid() == 321

    monkeypatch.setattr(pm, "is_running", lambda: True)
    assert pm.start(regenerate_config=False) == 321

    monkeypatch.setattr(pm, "is_running", lambda: False)
    monkeypatch.setattr(pm, "is_binary_present", lambda: False)
    with pytest.raises(FileNotFoundError):
        pm.start()

    monkeypatch.setattr(pm, "is_binary_present", lambda: True)

    class _CrashProc:
        pid = 456
        returncode = 9

        def poll(self):
            return 9

    monkeypatch.setattr(pm.subprocess, "Popen", lambda *a, **k: _CrashProc())
    with pytest.raises(RuntimeError, match="exited immediately"):
        pm.start()

    pm._write_pid(77)
    calls: list[tuple[int, int]] = []

    def _kill(pid, sig):
        calls.append((pid, sig))
        if sig == 0:
            raise ProcessLookupError

    monkeypatch.setattr(pm.os, "kill", _kill)
    pm.stop(timeout=0.1)
    assert pm._read_pid() is None

    monkeypatch.setattr(pm, "stop", lambda timeout=10.0: None)
    monkeypatch.setattr(pm, "start", lambda **kw: 999)
    assert pm.restart(public_ip="") == 999

    monkeypatch.setattr(pm, "_read_pid", lambda: None)
    monkeypatch.setattr(pm, "is_running", lambda: False)
    with pytest.raises(RuntimeError, match="not running"):
        pm.reload_config()

    monkeypatch.setattr(pm, "_read_pid", lambda: 100)
    monkeypatch.setattr(pm, "is_running", lambda: True)
    monkeypatch.setattr(pm.signal, "SIGHUP", 1, raising=False)
    monkeypatch.setattr(pm.os, "kill", lambda pid, sig: None)
    pm.reload_config()

    def _gone(pid, sig):
        raise ProcessLookupError

    monkeypatch.setattr(pm.os, "kill", _gone)
    monkeypatch.setattr(pm, "_clear_pid", lambda: None)
    with pytest.raises(RuntimeError, match="not found"):
        pm.reload_config()

    monkeypatch.setattr(pm, "get_pid", lambda: 1)
    monkeypatch.setattr(pm, "is_running", lambda: True)
    monkeypatch.setattr(pm, "is_binary_present", lambda: True)
    monkeypatch.setattr(pm, "TOML_CONFIG_FILE", SimpleNamespace(exists=lambda: True))
    monkeypatch.setitem(sys.modules, "psutil", SimpleNamespace(Process=lambda pid: SimpleNamespace(create_time=lambda: 0)))
    st = pm.status()
    assert st["running"] is True
    assert st["pid"] == 1
