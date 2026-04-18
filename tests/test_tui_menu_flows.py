from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import mtproxymaxpy
from mtproxymaxpy.tui import menu


def test_logs_and_health_screens(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    printed = []
    monkeypatch.setattr(menu.console, "print", lambda *a, **k: printed.append(a))
    monkeypatch.setattr(menu, "_clear", lambda: None)
    monkeypatch.setattr(menu, "_pause", lambda: None)
    monkeypatch.setattr(menu, "_header_panel", lambda: "H")

    log_file = tmp_path / "telemt.log"
    log_file.write_text("a\nb\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.constants", SimpleNamespace(INSTALL_DIR=tmp_path))
    menu._logs_screen()
    assert printed

    log_file.unlink()
    menu._logs_screen()

    _mock_doctor_ok = SimpleNamespace(run_full_doctor=lambda: [{"name": "A", "ok": True}, {"name": "B", "ok": False, "error": "x"}])
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.doctor", _mock_doctor_ok)
    monkeypatch.setattr(mtproxymaxpy, "doctor", _mock_doctor_ok)
    menu._health_screen()

    _mock_doctor_err = SimpleNamespace(run_full_doctor=lambda: (_ for _ in ()).throw(RuntimeError("bad")))
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.doctor", _mock_doctor_err)
    monkeypatch.setattr(mtproxymaxpy, "doctor", _mock_doctor_err)
    menu._health_screen()


def test_status_screen_success_and_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(menu, "_clear", lambda: None)
    monkeypatch.setattr(menu, "_pause", lambda: None)
    monkeypatch.setattr(menu, "_header_panel", lambda: "H")
    printed = []
    monkeypatch.setattr(menu.console, "print", lambda *a, **k: printed.append(a))

    _mock_pm = SimpleNamespace(status=lambda: {"running": True, "pid": 1, "uptime_sec": 60})
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.process_manager", _mock_pm)
    monkeypatch.setattr(mtproxymaxpy, "process_manager", _mock_pm)
    _mock_metrics = SimpleNamespace(
        get_stats=lambda: {
            "available": True,
            "bytes_in": 1,
            "bytes_out": 2,
            "active_connections": 3,
            "total_connections": 4,
        },
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.metrics", _mock_metrics)
    monkeypatch.setattr(mtproxymaxpy, "metrics", _mock_metrics)
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(load_settings=lambda: SimpleNamespace(proxy_port=443, proxy_domain="cf.com", custom_ip="", proxy_concurrency=1000)),
    )
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.secrets",
        SimpleNamespace(load_secrets=lambda: [SimpleNamespace(enabled=True, key="a" * 32)]),
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.network", SimpleNamespace(get_public_ip=lambda: "1.1.1.1"))
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.utils.formatting",
        SimpleNamespace(format_bytes=lambda n: f"{n}B", format_duration=lambda s: "1m"),
    )
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.utils.proxy_link",
        SimpleNamespace(build_proxy_links=lambda *a, **k: ("tg://x", "https://x")),
    )
    menu._status_screen()
    assert printed

    _mock_pm_err = SimpleNamespace(status=lambda: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.process_manager", _mock_pm_err)
    monkeypatch.setattr(mtproxymaxpy, "process_manager", _mock_pm_err)
    menu._status_screen()


def test_proxy_menu_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(menu, "_clear", lambda: None)
    monkeypatch.setattr(menu, "_header_panel", lambda: "H")
    monkeypatch.setattr(menu, "_pause", lambda: None)
    monkeypatch.setattr(menu.console, "print", lambda *a, **k: None)

    states = [True, True, True, True, True, True]
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.process_manager",
        SimpleNamespace(
            is_running=lambda: states.pop(0) if states else True,
            stop=lambda: None,
            restart=lambda public_ip="": 22,
            start=lambda public_ip="": 11,
        ),
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.network", SimpleNamespace(get_public_ip=lambda: "1.1.1.1"))

    called = {"logs": 0, "health": 0, "status": 0}
    monkeypatch.setattr(menu, "_logs_screen", lambda: called.__setitem__("logs", called["logs"] + 1))
    monkeypatch.setattr(menu, "_health_screen", lambda: called.__setitem__("health", called["health"] + 1))
    monkeypatch.setattr(menu, "_status_screen", lambda: called.__setitem__("status", called["status"] + 1))

    choices = iter([1, 2, 3, 4, 5, 0])
    monkeypatch.setattr(menu, "_ask_choice", lambda *a, **k: next(choices))
    menu._proxy_menu()
    assert called == {"logs": 1, "health": 1, "status": 1}


def test_run_tui_main_loop_routes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(menu, "_clear", lambda: None)
    monkeypatch.setattr(menu, "_check_update_bg", lambda wait_timeout=3.0: None)
    monkeypatch.setattr(menu, "_header_panel", lambda: "H")
    monkeypatch.setattr(menu.console, "print", lambda *a, **k: None)

    settings_file = tmp_path / "settings.toml"
    settings_file.write_text("x", encoding="utf-8")
    badge_file = tmp_path / "badge"
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.constants",
        SimpleNamespace(SETTINGS_FILE=settings_file, UPDATE_BADGE_FILE=badge_file),
    )

    monkeypatch.setitem(sys.modules, "mtproxymaxpy.config.secrets", SimpleNamespace(load_secrets=lambda: [1, 2]))
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.config.upstreams", SimpleNamespace(load_upstreams=lambda: [1]))
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(load_settings=lambda: SimpleNamespace(telegram_enabled=True, proxy_port=443, proxy_domain="cf.com")),
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.geoblock", SimpleNamespace(list_countries=lambda: ["RU"]))

    calls = {i: 0 for i in range(1, 11)}
    monkeypatch.setattr(menu, "_proxy_menu", lambda: calls.__setitem__(1, calls[1] + 1))
    monkeypatch.setattr(menu, "_secrets_menu", lambda: calls.__setitem__(2, calls[2] + 1))
    monkeypatch.setattr(menu, "_links_menu", lambda: calls.__setitem__(3, calls[3] + 1))
    monkeypatch.setattr(menu, "_upstreams_menu", lambda: calls.__setitem__(4, calls[4] + 1))
    monkeypatch.setattr(menu, "_settings_menu", lambda: calls.__setitem__(5, calls[5] + 1))
    monkeypatch.setattr(menu, "_logs_traffic_screen", lambda: calls.__setitem__(6, calls[6] + 1))
    monkeypatch.setattr(menu, "_geoblock_menu", lambda: calls.__setitem__(7, calls[7] + 1))
    monkeypatch.setattr(menu, "_backup_menu", lambda: calls.__setitem__(8, calls[8] + 1))
    monkeypatch.setattr(menu, "_telegram_menu", lambda: calls.__setitem__(9, calls[9] + 1))
    monkeypatch.setattr(menu, "_update_screen", lambda: calls.__setitem__(10, calls[10] + 1))

    choices = iter([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 0])
    monkeypatch.setattr(menu, "_ask_choice", lambda *a, **k: next(choices))
    menu.run_tui()
    assert all(v == 1 for v in calls.values())


def test_run_tui_setup_and_migration_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(menu, "_clear", lambda: None)
    monkeypatch.setattr(menu, "_check_update_bg", lambda wait_timeout=3.0: None)
    monkeypatch.setattr(menu, "_header_panel", lambda: "H")
    monkeypatch.setattr(menu.console, "print", lambda *a, **k: None)

    settings_file = tmp_path / "settings.toml"
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.constants",
        SimpleNamespace(SETTINGS_FILE=settings_file, UPDATE_BADGE_FILE=tmp_path / "badge"),
    )

    monkeypatch.setitem(sys.modules, "mtproxymaxpy.config.migration", SimpleNamespace(detect_legacy=lambda: ["settings.conf"]))
    called = {"mig": 0, "wiz": 0}
    monkeypatch.setattr(menu, "_migration_screen", lambda legacy: called.__setitem__("mig", called["mig"] + 1))
    monkeypatch.setattr(menu, "_setup_wizard", lambda: called.__setitem__("wiz", called["wiz"] + 1))
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.config.secrets", SimpleNamespace(load_secrets=lambda: []))
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.config.upstreams", SimpleNamespace(load_upstreams=lambda: []))
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(load_settings=lambda: SimpleNamespace(telegram_enabled=False, proxy_port=443, proxy_domain="cf.com")),
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.geoblock", SimpleNamespace(list_countries=lambda: []))
    monkeypatch.setattr(menu, "_ask_choice", lambda *a, **k: 0)
    menu.run_tui()
    assert called["mig"] == 1

    monkeypatch.setitem(sys.modules, "mtproxymaxpy.config.migration", SimpleNamespace(detect_legacy=lambda: []))
    menu.run_tui()
    assert called["wiz"] == 1
