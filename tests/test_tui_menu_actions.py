from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING

from mtproxymaxpy.tui import menu

if TYPE_CHECKING:
    import pytest


class _Settings:
    def __init__(self, **kw):
        defaults = {
            "proxy_port": 443,
            "proxy_domain": "cloudflare.com",
            "proxy_concurrency": 1000,
            "custom_ip": "",
            "ad_tag": "",
            "masking_enabled": True,
            "masking_host": "example.com",
            "unknown_sni_action": "mask",
            "proxy_protocol": False,
            "proxy_protocol_trusted_cidrs": "",
            "proxy_cpus": "",
            "proxy_memory": "",
            "auto_update_enabled": True,
            "geoblock_mode": "blacklist",
            "telegram_enabled": False,
            "telegram_bot_token": "",
            "telegram_chat_id": "",
            "telegram_interval": 24,
            "telegram_server_label": "srv",
        }
        defaults.update(kw)
        self.__dict__.update(defaults)

    def model_copy(self, update: dict):
        data = self.__dict__.copy()
        data.update(update)
        return _Settings(**data)


def test_secrets_action_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(menu, "_pause", lambda: None)
    monkeypatch.setattr(menu.console, "print", lambda *a, **k: None)

    called = {"add": 0, "link": 0, "enable": 0, "disable": 0, "rename": 0, "clone": 0, "note": 0, "limits": 0}
    monkeypatch.setattr(menu, "_secret_add", lambda: called.__setitem__("add", called["add"] + 1))
    monkeypatch.setattr(menu, "_secret_show_link", lambda secs: called.__setitem__("link", called["link"] + 1))

    prompts = iter(
        [
            "to-remove",  # ch2
            "to-rotate",  # ch3
            "alice",
            "enable",  # ch4 enable
            "alice",
            "disable",  # ch4 disable
            "alice",
            "1G",
            "",  # ch5
            "alice",  # ch6
            "rename",
            "a",
            "b",  # ch7 rename
            "clone",
            "b",
            "c",  # ch7 clone
            "alice",
            "memo",  # ch8
        ],
    )
    ints = iter([3, 2, 30])
    monkeypatch.setattr(menu.Prompt, "ask", lambda *a, **k: next(prompts))
    monkeypatch.setattr(menu.IntPrompt, "ask", lambda *a, **k: next(ints))

    sec_mod = SimpleNamespace(
        remove_secret=lambda label: True,
        rotate_secret=lambda label: SimpleNamespace(key="k" * 32),
        enable_secret=lambda label: called.__setitem__("enable", called["enable"] + 1),
        disable_secret=lambda label: called.__setitem__("disable", called["disable"] + 1),
        set_secret_limits=lambda *a, **k: called.__setitem__("limits", called["limits"] + 1),
        extend_secret=lambda label, days: SimpleNamespace(expires="2030-01-01"),
        rename_secret=lambda old, new: called.__setitem__("rename", called["rename"] + 1),
        clone_secret=lambda old, new: called.__setitem__("clone", called["clone"] + 1),
        set_secret_note=lambda label, text: called.__setitem__("note", called["note"] + 1),
        export_secrets_csv=lambda: "label,key\n",
        disable_expired_secrets=lambda: [1, 2],
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.config.secrets", sec_mod)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.validation", SimpleNamespace(parse_human_bytes=lambda x: 1024**3))

    secs = [SimpleNamespace(label="alice", key="a" * 32, enabled=True)]
    menu._secrets_action(1, secs)
    menu._secrets_action(2, secs)
    menu._secrets_action(3, secs)
    menu._secrets_action(4, secs)
    menu._secrets_action(4, secs)
    menu._secrets_action(5, secs)
    menu._secrets_action(6, secs)
    menu._secrets_action(7, secs)
    menu._secrets_action(7, secs)
    menu._secrets_action(8, secs)
    menu._secrets_action(9, secs)
    menu._secrets_action(10, secs)
    menu._secrets_action(11, secs)

    assert called["add"] == 1
    assert called["link"] == 1
    assert called["enable"] == 1
    assert called["disable"] == 1
    assert called["rename"] == 1
    assert called["clone"] == 1
    assert called["note"] == 1
    assert called["limits"] == 1


def test_secret_show_link_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(menu, "_pause", lambda: None)
    monkeypatch.setattr(menu.console, "print", lambda *a, **k: None)

    secs = [SimpleNamespace(label="u1", key="a" * 32, enabled=True)]
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(load_settings=lambda: SimpleNamespace(custom_ip="", proxy_domain="cf.com", proxy_port=443)),
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.network", SimpleNamespace(get_public_ip=lambda: "1.2.3.4"))
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.utils.proxy_link",
        SimpleNamespace(build_proxy_links=lambda *a, **k: ("tg://x", "https://x"), render_qr_terminal=lambda t: "QR"),
    )

    monkeypatch.setattr(menu.Prompt, "ask", lambda *a, **k: "")
    menu._secret_show_link(secs)

    monkeypatch.setattr(menu.Prompt, "ask", lambda *a, **k: "missing")
    menu._secret_show_link(secs)


def test_links_menu_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(menu, "_clear", lambda: None)
    monkeypatch.setattr(menu, "_pause", lambda: None)
    monkeypatch.setattr(menu, "_header_panel", lambda: "H")
    monkeypatch.setattr(menu.console, "print", lambda *a, **k: None)

    called = {"show": 0}
    monkeypatch.setattr(menu, "_secret_show_link", lambda secs: called.__setitem__("show", called["show"] + 1))

    # ch=2 path, then back
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.secrets",
        SimpleNamespace(load_secrets=lambda: [SimpleNamespace(enabled=True, key="a" * 32, label="u1")]),
    )
    choices = iter([2, 0])
    monkeypatch.setattr(menu, "_ask_choice", lambda *a, **k: next(choices))
    menu._links_menu()
    assert called["show"] == 1

    # ch=1 path with no enabled
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.config.secrets", SimpleNamespace(load_secrets=list))
    choices = iter([1, 0])
    monkeypatch.setattr(menu, "_ask_choice", lambda *a, **k: next(choices))
    menu._links_menu()

    # ch=1 path, enabled present, but no ip
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.secrets",
        SimpleNamespace(load_secrets=lambda: [SimpleNamespace(enabled=True, key="a" * 32, label="u1")]),
    )
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(load_settings=lambda: SimpleNamespace(custom_ip="", proxy_domain="cf.com", proxy_port=443)),
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.network", SimpleNamespace(get_public_ip=lambda: ""))
    choices = iter([1, 0])
    monkeypatch.setattr(menu, "_ask_choice", lambda *a, **k: next(choices))
    menu._links_menu()

    # ch=1 path with links and qr
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.network", SimpleNamespace(get_public_ip=lambda: "1.2.3.4"))
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.utils.proxy_link",
        SimpleNamespace(build_proxy_links=lambda *a, **k: ("tg://x", "https://x"), render_qr_terminal=lambda t: "QR"),
    )
    choices = iter([1, 0])
    monkeypatch.setattr(menu, "_ask_choice", lambda *a, **k: next(choices))
    menu._links_menu()


def test_upstreams_action_and_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(menu, "_pause", lambda: None)
    monkeypatch.setattr(menu.console, "print", lambda *a, **k: None)

    ups_calls = {"add": 0, "remove": 0, "toggle": 0, "test": 0, "restart": 0}
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.upstreams",
        SimpleNamespace(
            add_upstream=lambda *a, **k: ups_calls.__setitem__("add", ups_calls["add"] + 1),
            remove_upstream=lambda name: ups_calls.__setitem__("remove", ups_calls["remove"] + 1),
            toggle_upstream=lambda name: SimpleNamespace(enabled=False),
            test_upstream=lambda name: {"ok": True, "latency_ms": 12, "error": None},
        ),
    )

    import mtproxymaxpy as pkg

    pm = SimpleNamespace(is_running=lambda: True, restart=lambda public_ip="": 99)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.process_manager", pm)
    monkeypatch.setattr(pkg, "process_manager", pm, raising=False)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.network", SimpleNamespace(get_public_ip=lambda: "1.2.3.4"))

    prompts = iter(["u1", "socks5", "127.0.0.1:1080", "", "", "u1", "u1", "u1", "u1"])
    monkeypatch.setattr(menu.Prompt, "ask", lambda *a, **k: next(prompts))
    monkeypatch.setattr(menu.IntPrompt, "ask", lambda *a, **k: 10)

    menu._upstreams_action(1, [])
    menu._upstreams_action(2, [])
    menu._upstreams_action(3, [])
    menu._upstreams_action(4, [])
    assert ups_calls["add"] == 1
    assert ups_calls["remove"] == 1

    # failure path for test
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.upstreams",
        SimpleNamespace(test_upstream=lambda name: {"ok": False, "error": "bad", "latency_ms": None}),
    )
    monkeypatch.setattr(menu.Prompt, "ask", lambda *a, **k: "u1")
    menu._upstreams_action(4, [])

    # restart helper branch when not running
    pm2 = SimpleNamespace(is_running=lambda: False, restart=lambda public_ip="": 1)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.process_manager", pm2)
    monkeypatch.setattr(pkg, "process_manager", pm2, raising=False)
    menu._restart_proxy_if_running()


def test_settings_menu_save_and_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(menu, "_clear", lambda: None)
    monkeypatch.setattr(menu, "_pause", lambda: None)
    monkeypatch.setattr(menu, "_header_panel", lambda: "H")
    monkeypatch.setattr(menu.console, "print", lambda *a, **k: None)

    state = {"settings": _Settings(), "saved": []}

    def _load():
        return state["settings"]

    def _save(s):
        state["saved"].append(s)
        state["settings"] = s

    monkeypatch.setitem(sys.modules, "mtproxymaxpy.config.settings", SimpleNamespace(load_settings=_load, save_settings=_save))

    choices = iter([1, 6, 18, 0])
    monkeypatch.setattr(menu, "_ask_choice", lambda *a, **k: next(choices))
    values = iter(["8443", "false", "bad"])  # third causes int conversion error branch
    monkeypatch.setattr(menu.Prompt, "ask", lambda *a, **k: next(values))
    menu._settings_menu()

    assert state["saved"][0].proxy_port == 8443
    assert state["saved"][1].masking_enabled is False
