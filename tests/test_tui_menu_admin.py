from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from mtproxymaxpy.tui import menu


class _Settings:
    def __init__(self, **kw):
        defaults = {
            "telegram_enabled": False,
            "telegram_bot_token": "",
            "telegram_chat_id": "",
            "telegram_interval": 24,
            "telegram_alerts_enabled": True,
            "telegram_server_label": "srv",
            "proxy_port": 443,
            "proxy_domain": "cloudflare.com",
            "custom_ip": "",
            "masking_enabled": True,
            "ad_tag": "",
            "masking_host": "",
        }
        defaults.update(kw)
        self.__dict__.update(defaults)

    def model_copy(self, update: dict):
        data = self.__dict__.copy()
        data.update(update)
        return _Settings(**data)


def _mute_ui(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(menu, "_clear", lambda: None)
    monkeypatch.setattr(menu, "_pause", lambda: None)
    monkeypatch.setattr(menu, "_header_panel", lambda: "H")
    monkeypatch.setattr(menu.console, "print", lambda *a, **k: None)


def test_geoblock_menu_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    _mute_ui(monkeypatch)
    import mtproxymaxpy as pkg

    calls = {"add": 0, "remove": 0, "re": 0, "clear": 0}
    geo = SimpleNamespace(
        list_countries=lambda: ["RU"],
        add_country=lambda cc: calls.__setitem__("add", calls["add"] + 1) or 5,
        remove_country=lambda cc: calls.__setitem__("remove", calls["remove"] + 1),
        reapply_all=lambda: calls.__setitem__("re", calls["re"] + 1),
        clear_all=lambda: calls.__setitem__("clear", calls["clear"] + 1),
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.geoblock", geo)
    monkeypatch.setattr(pkg, "geoblock", geo, raising=False)

    choices = iter([1, 2, 3, 4, 0])
    prompts = iter(["ru", "ru"])
    monkeypatch.setattr(menu, "_ask_choice", lambda *a, **k: next(choices))
    monkeypatch.setattr(menu.Prompt, "ask", lambda *a, **k: next(prompts))
    monkeypatch.setattr(menu.Confirm, "ask", lambda *a, **k: True)
    menu._geoblock_menu()
    assert calls == {"add": 1, "remove": 1, "re": 1, "clear": 1}


def test_backup_menu_and_migration_screen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _mute_ui(monkeypatch)
    import mtproxymaxpy as pkg

    bkp = SimpleNamespace(
        list_backups=lambda: [{"name": "b.tar.gz", "size": 1024, "mtime": datetime(2026, 1, 1)}],
        create_backup=lambda label="": tmp_path / "b.tar.gz",
        restore_backup=lambda path: {"version": "1.0"},
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.backup", bkp)
    monkeypatch.setattr(pkg, "backup", bkp, raising=False)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.formatting", SimpleNamespace(format_bytes=lambda n: f"{n}B"))
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.constants", SimpleNamespace(BACKUP_DIR=tmp_path))

    choices = iter([1, 2, 0])
    prompts = iter(["manual", "b.tar.gz"])
    monkeypatch.setattr(menu, "_ask_choice", lambda *a, **k: next(choices))
    monkeypatch.setattr(menu.Prompt, "ask", lambda *a, **k: next(prompts))
    monkeypatch.setattr(menu.Confirm, "ask", lambda *a, **k: True)
    menu._backup_menu()

    monkeypatch.setitem(sys.modules, "mtproxymaxpy.config.migration", SimpleNamespace(run_migration=lambda legacy: {"ok": True}))
    monkeypatch.setattr(menu.Confirm, "ask", lambda *a, **k: True)
    menu._migration_screen({"settings": tmp_path / "settings.conf"})


def test_telegram_menu_and_helpers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _mute_ui(monkeypatch)
    import mtproxymaxpy as pkg

    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    service_name = "mtproxymaxpy-telegram"
    (unit_dir / f"{service_name}.service").write_text("x", encoding="utf-8")

    state = {"settings": _Settings(telegram_enabled=True, telegram_bot_token="tok_12345", telegram_chat_id="1")}

    def _load_settings():
        return state["settings"]

    def _save_settings(s):
        state["settings"] = s

    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.constants",
        SimpleNamespace(SYSTEMD_TELEGRAM_SERVICE=service_name, SYSTEMD_UNIT_DIR=unit_dir),
    )
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(load_settings=_load_settings, save_settings=_save_settings),
    )

    calls = {"start": 0, "stop": 0, "install": 0, "wizard": 0, "test": 0, "tg_logs": 0}
    sd = SimpleNamespace(
        is_active=lambda name: False,
        install_telegram_service=lambda: calls.__setitem__("install", calls["install"] + 1),
        start_service=lambda name: calls.__setitem__("start", calls["start"] + 1),
        stop_service=lambda name: calls.__setitem__("stop", calls["stop"] + 1),
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.systemd", sd)
    monkeypatch.setattr(pkg, "systemd", sd, raising=False)
    real_wizard = menu._telegram_setup_wizard
    real_test = menu._telegram_test
    monkeypatch.setattr(menu, "_telegram_setup_wizard", lambda: calls.__setitem__("wizard", calls["wizard"] + 1))
    monkeypatch.setattr(menu, "_telegram_test", lambda: calls.__setitem__("test", calls["test"] + 1))
    monkeypatch.setattr(menu, "_stream_telegram_logs_screen", lambda: calls.__setitem__("tg_logs", calls["tg_logs"] + 1))
    monkeypatch.setattr(menu.IntPrompt, "ask", lambda *a, **k: 12)

    choices = iter([1, 2, 3, 4, 5, 6, 7, 0])
    monkeypatch.setattr(menu, "_ask_choice", lambda *a, **k: next(choices))
    menu._telegram_menu()

    assert calls["wizard"] == 1
    assert calls["test"] == 1
    assert calls["install"] >= 1
    assert calls["tg_logs"] == 1

    # _telegram_setup_wizard real path
    prompts = iter(["token", "chat", "node-1"])
    monkeypatch.setattr(menu.Prompt, "ask", lambda *a, **k: next(prompts))
    real_wizard()
    assert state["settings"].telegram_enabled is True
    assert state["settings"].telegram_server_label == "node-1"

    # _telegram_test branches: missing config and success/failure send
    state["settings"] = _Settings(telegram_enabled=True, telegram_bot_token="", telegram_chat_id="")
    real_test()

    state["settings"] = _Settings(telegram_enabled=True, telegram_bot_token="tok", telegram_chat_id="1")

    class _AioBot:
        def __init__(self, token):
            async def _close():
                return None

            self.session = SimpleNamespace(close=_close)

        async def send_message(self, cid, text):
            return None

    monkeypatch.setitem(
        sys.modules,
        "aiogram",
        SimpleNamespace(Bot=_AioBot),
    )
    real_test()

    class _AioBotFail:
        def __init__(self, token):
            async def _close():
                return None

            self.session = SimpleNamespace(close=_close)

        async def send_message(self, cid, text):
            raise RuntimeError("bad")

    monkeypatch.setitem(
        sys.modules,
        "aiogram",
        SimpleNamespace(Bot=_AioBotFail),
    )
    real_test()


def test_update_and_setup_wizard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _mute_ui(monkeypatch)
    import mtproxymaxpy as pkg

    install_dir = tmp_path / "install"
    install_dir.mkdir()
    sha_file = tmp_path / "sha"
    badge_file = tmp_path / "badge"
    binary_path = tmp_path / "telemt"

    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.constants",
        SimpleNamespace(
            GITHUB_REPO="owner/repo",
            GITHUB_API_COMMITS="https://api.example/commits",
            INSTALL_DIR=install_dir,
            UPDATE_SHA_FILE=sha_file,
            UPDATE_BADGE_FILE=badge_file,
            VERSION="1.0.0",
            TELEMT_VERSION="1.2.3",
            BINARY_PATH=binary_path,
            SYSTEMD_TELEGRAM_SERVICE="mtproxymaxpy-telegram",
            SYSTEMD_UNIT_DIR=tmp_path,
        ),
    )

    # up-to-date branch + engine up-to-date
    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(get=lambda *a, **k: SimpleNamespace(text="a" * 40)))

    def _sub_run(cmd, **kwargs):
        if "rev-parse" in cmd:
            return SimpleNamespace(returncode=0, stdout="a" * 40, stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setitem(sys.modules, "subprocess", SimpleNamespace(run=_sub_run))
    pm = SimpleNamespace(
        get_latest_version=lambda: "1.2.3",
        is_running=lambda: False,
        stop=lambda: None,
        download_binary=lambda **k: None,
        start=lambda public_ip="": 1,
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.process_manager", pm)
    monkeypatch.setattr(pkg, "process_manager", pm, raising=False)
    monkeypatch.setattr(menu.Confirm, "ask", lambda *a, **k: False)
    menu._update_screen()

    # setup wizard happy path
    saved = {"settings": None, "secret": None}

    class _SettingsModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(
            Settings=_SettingsModel,
            save_settings=lambda s: saved.__setitem__("settings", s),
            load_settings=lambda: _Settings(),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.secrets",
        SimpleNamespace(add_secret=lambda label: SimpleNamespace(label=label, key="a" * 32)),
    )
    pm2 = SimpleNamespace(download_binary=lambda **k: None, start=lambda public_ip="": 123)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.process_manager", pm2)
    monkeypatch.setattr(pkg, "process_manager", pm2, raising=False)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.systemd", SimpleNamespace(install=lambda: None))
    monkeypatch.setattr(pkg, "systemd", SimpleNamespace(install=lambda: None), raising=False)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.network", SimpleNamespace(get_public_ip=lambda: "1.2.3.4"))
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.utils.proxy_link",
        SimpleNamespace(build_proxy_links=lambda *a, **k: ("tg://x", "https://x")),
    )

    prompts = iter(["1.2.3.4", "my.domain", "TAG", "user1"])
    confirms = iter([True, True, False])  # masking yes, ad-tag yes, telegram setup no
    monkeypatch.setattr(menu.IntPrompt, "ask", lambda *a, **k: 443 if "port" in a[0].lower() else len(menu.FAKETLS_DOMAINS))
    monkeypatch.setattr(menu.Prompt, "ask", lambda *a, **k: next(prompts))
    monkeypatch.setattr(menu.Confirm, "ask", lambda *a, **k: next(confirms))
    menu._setup_wizard()
