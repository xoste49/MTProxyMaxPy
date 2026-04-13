from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import mtproxymaxpy.__main__ as entry
from mtproxymaxpy.utils import network, system


class _Resp:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self) -> None:
        return None


def test_main_dispatches_to_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"n": 0}
    fake_cli = SimpleNamespace(app=lambda: called.__setitem__("n", called["n"] + 1))
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.cli", fake_cli)
    monkeypatch.setattr(sys, "argv", ["mtproxymaxpy", "status"])

    entry.main()
    assert called["n"] == 1


def test_main_dispatches_to_tui(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"n": 0}
    fake_tui = SimpleNamespace(run_tui=lambda: called.__setitem__("n", called["n"] + 1))
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.tui.app", fake_tui)
    monkeypatch.setattr(sys, "argv", ["mtproxymaxpy"])

    entry.main()
    assert called["n"] == 1


def test_main_module_dunder_main_invokes_main(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"n": 0}
    fake_tui = SimpleNamespace(run_tui=lambda: called.__setitem__("n", called["n"] + 1))
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.tui.app", fake_tui)
    monkeypatch.delitem(sys.modules, "mtproxymaxpy.__main__", raising=False)
    monkeypatch.setattr(sys, "argv", ["mtproxymaxpy"])

    runpy.run_module("mtproxymaxpy.__main__", run_name="__main__")
    assert called["n"] == 1


def test_network_get_public_ip_and_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    network._ip_cache = None
    monkeypatch.setattr(network, "PUBLIC_IP_ENDPOINTS", ["a", "b"])

    calls = {"n": 0}

    def _fake_get(url, timeout, follow_redirects):
        calls["n"] += 1
        if url == "a":
            raise RuntimeError("fail")
        return _Resp('{"ip":"1.2.3.4"}')

    t = {"v": 10.0}
    monkeypatch.setattr(network.httpx, "get", _fake_get)
    monkeypatch.setattr(network.time, "monotonic", lambda: t["v"])

    assert network.get_public_ip() == "1.2.3.4"
    assert calls["n"] == 2

    t["v"] = 11.0
    assert network.get_public_ip() == "1.2.3.4"
    assert calls["n"] == 2


def test_network_get_public_ip_none_if_all_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    network._ip_cache = None
    monkeypatch.setattr(network, "PUBLIC_IP_ENDPOINTS", ["a"])
    monkeypatch.setattr(network.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert network.get_public_ip() is None


def test_check_root_paths(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(system.os, "geteuid", lambda: 0, raising=False)
    system.check_root()

    monkeypatch.setattr(system.os, "geteuid", lambda: 1000, raising=False)
    with pytest.raises(SystemExit) as exc:
        system.check_root()
    assert exc.value.code == 1
    assert "must be run as root" in capsys.readouterr().err


def test_detect_os_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    class _P:
        def __init__(self, text: str, exists: bool = True):
            self._text = text
            self._exists = exists

        def exists(self):
            return self._exists

        def read_text(self):
            return self._text

    monkeypatch.setattr(system, "Path", lambda _p: _P("ID=ubuntu"))
    assert system.detect_os() == "debian"

    monkeypatch.setattr(system, "Path", lambda _p: _P("ID=fedora"))
    assert system.detect_os() == "rhel"

    monkeypatch.setattr(system, "Path", lambda _p: _P("ID=alpine"))
    assert system.detect_os() == "alpine"

    monkeypatch.setattr(system, "Path", lambda _p: _P("", exists=False))
    assert system.detect_os() == "unknown"


def test_check_dependencies_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        system.shutil, "which", lambda name: "/bin/x" if name in {"curl", "awk", "openssl", "ss"} else None
    )
    assert system.check_dependencies() == []

    monkeypatch.setattr(system.shutil, "which", lambda name: None)
    monkeypatch.setattr(system, "detect_os", lambda: "unknown")
    missing = system.check_dependencies()
    assert "curl" in missing
    assert "iproute2" in missing

    state = {"installed": False}

    def _which(name: str):
        if state["installed"]:
            return "/bin/x"
        return None

    def _run(cmd, check, capture_output):
        state["installed"] = True
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(system.shutil, "which", _which)
    monkeypatch.setattr(system, "detect_os", lambda: "debian")
    monkeypatch.setattr(system.subprocess, "run", _run)
    assert system.check_dependencies() == []

    monkeypatch.setattr(
        system.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(subprocess.CalledProcessError(1, ["apt-get"])),
    )
    state["installed"] = False
    out = system.check_dependencies()
    assert "curl" in out


def test_get_arch_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    assert system.get_arch() == "x86_64"

    monkeypatch.setattr("platform.machine", lambda: "arm64")
    assert system.get_arch() == "aarch64"

    monkeypatch.setattr("platform.machine", lambda: "mips")
    with pytest.raises(RuntimeError, match="Unsupported architecture"):
        system.get_arch()
