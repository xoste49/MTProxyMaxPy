from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING

from mtproxymaxpy.tui import menu

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_metrics_screen_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(menu, "_clear", lambda: None)
    monkeypatch.setattr(menu, "_pause", lambda: None)
    monkeypatch.setattr(menu, "_header_panel", lambda: "H")
    monkeypatch.setattr(menu.console, "print", lambda *a, **k: None)

    monkeypatch.setitem(sys.modules, "mtproxymaxpy.metrics", SimpleNamespace(get_stats=lambda: {"available": False, "error": "x"}))
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.formatting", SimpleNamespace(format_bytes=lambda n: f"{n}B"))
    menu._metrics_screen()

    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.metrics",
        SimpleNamespace(
            get_stats=lambda: {
                "available": True,
                "bytes_in": 1,
                "bytes_out": 2,
                "active_connections": 3,
                "total_connections": 4,
                "user_stats": {"a" * 32: {"bytes_in": 10, "bytes_out": 20, "active": 1}},
            },
        ),
    )
    menu._metrics_screen()

    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.metrics",
        SimpleNamespace(get_stats=lambda: (_ for _ in ()).throw(RuntimeError("boom"))),
    )
    menu._metrics_screen()


def test_stream_live_logs_screen_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(menu, "_clear", lambda: None)
    monkeypatch.setattr(menu, "_pause", lambda: None)
    monkeypatch.setattr(menu, "_header_panel", lambda: "H")
    monkeypatch.setattr(menu.console, "print", lambda *a, **k: None)

    # missing file branch
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.constants", SimpleNamespace(INSTALL_DIR=tmp_path))
    menu._stream_live_logs_screen()

    # live loop exits by KeyboardInterrupt
    log = tmp_path / "telemt.log"
    log.write_text("a\nb\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.constants", SimpleNamespace(INSTALL_DIR=tmp_path))
    monkeypatch.setattr(menu.time, "sleep", lambda s: (_ for _ in ()).throw(KeyboardInterrupt()))
    menu._stream_live_logs_screen()


def test_connection_and_active_screens(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(menu, "_clear", lambda: None)
    monkeypatch.setattr(menu, "_pause", lambda: None)
    monkeypatch.setattr(menu, "_header_panel", lambda: "H")
    monkeypatch.setattr(menu.console, "print", lambda *a, **k: None)

    conn = tmp_path / "connection.log"
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.constants", SimpleNamespace(CONNECTION_LOG=conn))

    menu._connection_log_screen()
    conn.write_text("line1\nline2\n", encoding="utf-8")
    menu._connection_log_screen()

    monkeypatch.setitem(sys.modules, "mtproxymaxpy.metrics", SimpleNamespace(get_stats=lambda: {"available": False, "error": "x"}))
    menu._active_connections_screen()

    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.metrics",
        SimpleNamespace(get_stats=lambda: {"available": True, "active_connections": 2, "user_stats": {}}),
    )
    menu._active_connections_screen()

    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.metrics",
        SimpleNamespace(get_stats=lambda: {"available": True, "active_connections": 3, "user_stats": {"a" * 32: {"active": 2}}}),
    )
    menu._active_connections_screen()


def test_metrics_live_screen_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(menu, "_clear", lambda: None)
    monkeypatch.setattr(menu, "_header_panel", lambda: "H")
    monkeypatch.setattr(menu.console, "print", lambda *a, **k: None)

    monkeypatch.setitem(sys.modules, "mtproxymaxpy.metrics", SimpleNamespace(get_stats=lambda: {"available": False, "error": "x"}))
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.formatting", SimpleNamespace(format_bytes=lambda n: f"{n}B"))
    monkeypatch.setattr(menu.time, "sleep", lambda s: (_ for _ in ()).throw(KeyboardInterrupt()))
    menu._metrics_live_screen()

    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.metrics",
        SimpleNamespace(
            get_stats=lambda: {
                "available": True,
                "bytes_in": 1,
                "bytes_out": 2,
                "active_connections": 3,
                "total_connections": 4,
            },
        ),
    )
    monkeypatch.setattr(menu.time, "sleep", lambda s: (_ for _ in ()).throw(KeyboardInterrupt()))
    menu._metrics_live_screen()


def test_logs_traffic_screen_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(menu, "_clear", lambda: None)
    monkeypatch.setattr(menu, "_pause", lambda: None)
    monkeypatch.setattr(menu, "_header_panel", lambda: "H")
    monkeypatch.setattr(menu.console, "print", lambda *a, **k: None)

    import mtproxymaxpy as pkg

    # not running path
    pm = SimpleNamespace(is_running=lambda: False)
    met = SimpleNamespace(get_stats=lambda: {"available": True})
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.process_manager", pm)
    monkeypatch.setattr(pkg, "process_manager", pm, raising=False)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.metrics", met)
    monkeypatch.setattr(pkg, "metrics", met, raising=False)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.config.secrets", SimpleNamespace(load_secrets=list))
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.formatting", SimpleNamespace(format_bytes=lambda n: f"{n}B"))
    menu._logs_traffic_screen()

    # running + unavailable metrics + no users
    pm2 = SimpleNamespace(is_running=lambda: True)
    met2 = SimpleNamespace(get_stats=lambda: {"available": False, "error": "x"})
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.process_manager", pm2)
    monkeypatch.setattr(pkg, "process_manager", pm2, raising=False)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.metrics", met2)
    monkeypatch.setattr(pkg, "metrics", met2, raising=False)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.config.secrets", SimpleNamespace(load_secrets=list))
    monkeypatch.setattr(menu, "_ask_choice", lambda *a, **k: 0)
    menu._logs_traffic_screen()

    # running + available metrics + users + dispatch choices
    met3 = SimpleNamespace(
        get_stats=lambda: {
            "available": True,
            "bytes_in": 1,
            "bytes_out": 2,
            "active_connections": 3,
            "user_stats": {"a" * 32: {"bytes_in": 1, "bytes_out": 2, "active": 1}},
        },
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.metrics", met3)
    monkeypatch.setattr(pkg, "metrics", met3, raising=False)
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.secrets",
        SimpleNamespace(load_secrets=lambda: [SimpleNamespace(enabled=True, label="u1", key="a" * 32)]),
    )

    calls = {"l": 0, "c": 0, "m": 0, "ml": 0, "a": 0}
    monkeypatch.setattr(menu, "_stream_live_logs_screen", lambda: calls.__setitem__("l", calls["l"] + 1))
    monkeypatch.setattr(menu, "_connection_log_screen", lambda: calls.__setitem__("c", calls["c"] + 1))
    monkeypatch.setattr(menu, "_metrics_screen", lambda: calls.__setitem__("m", calls["m"] + 1))
    monkeypatch.setattr(menu, "_metrics_live_screen", lambda: calls.__setitem__("ml", calls["ml"] + 1))
    monkeypatch.setattr(menu, "_active_connections_screen", lambda: calls.__setitem__("a", calls["a"] + 1))

    for choice in (1, 2, 3, 4, 5):
        monkeypatch.setattr(menu, "_ask_choice", lambda *a, _choice=choice, **k: _choice)
        menu._logs_traffic_screen()

    assert calls == {"l": 1, "c": 1, "m": 1, "ml": 1, "a": 1}


def test_logs_traffic_screen_uses_label_keyed_user_stats(monkeypatch: pytest.MonkeyPatch) -> None:
    rendered: list[str] = []

    def _capture_print(*args, **kwargs) -> None:
        rendered.append(" ".join(str(a) for a in args))

    monkeypatch.setattr(menu, "_clear", lambda: None)
    monkeypatch.setattr(menu, "_pause", lambda: None)
    monkeypatch.setattr(menu, "_header_panel", lambda: "H")
    monkeypatch.setattr(menu.console, "print", _capture_print)
    monkeypatch.setattr(menu, "_ask_choice", lambda *a, **k: 0)

    import mtproxymaxpy as pkg

    pm = SimpleNamespace(is_running=lambda: True)
    met = SimpleNamespace(
        get_stats=lambda: {
            "available": True,
            "bytes_in": 10,
            "bytes_out": 20,
            "active_connections": 2,
            "user_stats": {
                "me": {"bytes_in": 1, "bytes_out": 2, "active": 3},
            },
        },
    )

    monkeypatch.setitem(sys.modules, "mtproxymaxpy.process_manager", pm)
    monkeypatch.setattr(pkg, "process_manager", pm, raising=False)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.metrics", met)
    monkeypatch.setattr(pkg, "metrics", met, raising=False)
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.secrets",
        SimpleNamespace(load_secrets=lambda: [SimpleNamespace(enabled=True, label="me", key="a" * 32)]),
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.formatting", SimpleNamespace(format_bytes=lambda n: f"{n} B"))

    menu._logs_traffic_screen()

    payload = "\n".join(rendered)
    assert "↓ 1 B  ↑ 2 B  conns: 3" in payload
