from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from mtproxymaxpy.tui import menu


def test_basic_menu_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"clear": 0, "print": 0}
    monkeypatch.setattr(menu.console, "clear", lambda: calls.__setitem__("clear", calls["clear"] + 1))
    monkeypatch.setattr(menu.console, "print", lambda *a, **k: calls.__setitem__("print", calls["print"] + 1))
    monkeypatch.setattr(menu.Prompt, "ask", lambda *a, **k: "")

    menu._clear()
    menu._pause()
    assert calls["clear"] == 1
    assert calls["print"] == 0

    line = menu._choice(3, "Label", "hint")
    assert "3" in line and "Label" in line and "hint" in line


def test_ask_choice_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter(["bad", "99", "2"])
    printed = {"n": 0}
    monkeypatch.setattr(menu.Prompt, "ask", lambda *a, **k: next(answers))
    monkeypatch.setattr(menu.console, "print", lambda *a, **k: printed.__setitem__("n", printed["n"] + 1))

    out = menu._ask_choice(3)
    assert out == 2
    assert printed["n"] >= 2


def test_header_panel_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import mtproxymaxpy as pkg

    pm = SimpleNamespace(status=lambda: {"running": True, "pid": 123, "uptime_sec": 60})
    sd = SimpleNamespace(is_active=lambda name: True)
    _mock_metrics = SimpleNamespace(
        get_stats=lambda **_kw: {"available": True, "bytes_in": 0, "bytes_out": 0, "active_connections": 0, "total_connections": 0},
    )
    _mock_secrets = SimpleNamespace(load_secrets=lambda: [])
    _mock_formatting = SimpleNamespace(format_bytes=lambda n: f"{n}B", format_duration=lambda s: "0s")

    monkeypatch.setattr(pkg, "process_manager", pm, raising=False)
    monkeypatch.setattr(pkg, "systemd", sd, raising=False)
    monkeypatch.setattr(pkg, "metrics", _mock_metrics, raising=False)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.process_manager", pm)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.systemd", sd)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.metrics", _mock_metrics)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.config.secrets", _mock_secrets)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.formatting", _mock_formatting)
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(load_settings=lambda: SimpleNamespace(proxy_port=443, telegram_enabled=True, proxy_metrics_port=9090, proxy_domain="cf.com")),
    )

    badge = tmp_path / "badge"
    badge.write_text("new", encoding="utf-8")
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.constants",
        SimpleNamespace(
            SYSTEMD_TELEGRAM_SERVICE="tg",
            SYSTEMD_UNIT_DIR=tmp_path,
            UPDATE_BADGE_FILE=badge,
        ),
    )
    (tmp_path / "tg.service").write_text("x", encoding="utf-8")
    panel = menu._header_panel()
    assert panel is not None

    # Fallback branch when imports fail inside header generation
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.process_manager",
        SimpleNamespace(status=lambda: (_ for _ in ()).throw(RuntimeError("x"))),
    )
    panel2 = menu._header_panel()
    assert panel2 is not None


def test_check_update_bg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    badge = tmp_path / "badge"
    sha_file = tmp_path / "sha"

    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.constants",
        SimpleNamespace(
            GITHUB_API_COMMITS="https://example/api",
            UPDATE_BADGE_FILE=badge,
            UPDATE_SHA_FILE=sha_file,
            INSTALL_DIR=tmp_path,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(load_settings=lambda: SimpleNamespace(manager_update_branch="main")),
    )

    class _Resp:
        text = "a" * 40

    monkeypatch.setattr(menu, "httpx", SimpleNamespace(get=lambda *a, **k: _Resp(), HTTPError=Exception))

    class _Thread:
        def __init__(self, target=None, daemon=True):
            self.target = target

        def start(self):
            if self.target:
                self.target()

        def join(self, timeout=None):
            return None

    monkeypatch.setattr(menu, "threading", SimpleNamespace(Thread=_Thread), raising=False)

    # No local git SHA and no stored SHA: should initialize stored SHA, no badge.
    monkeypatch.setattr("subprocess.run", lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr=""))
    menu._check_update_bg(wait_timeout=0.1)
    assert sha_file.exists()

    # Different stored SHA should set badge.
    sha_file.write_text("b" * 40, encoding="utf-8")
    menu._check_update_bg(wait_timeout=0.1)
    assert badge.exists()
