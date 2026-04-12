from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from mtproxymaxpy import telegram_bot


class _Msg:
    def __init__(self, chat_id: int, text: str):
        self.chat = SimpleNamespace(id=chat_id)
        self.text = text


class _Bot:
    def __init__(self):
        self.handlers: dict[str, object] = {}
        self.sent: list[tuple[str, str, str | None]] = []
        self.commands = None
        self.stopped = False
        self.polled = False

    def message_handler(self, commands=None):
        def _decorator(fn):
            for c in commands or []:
                self.handlers[c] = fn
            return fn

        return _decorator

    def send_message(self, chat_id: str, text: str, parse_mode=None):
        self.sent.append((chat_id, text, parse_mode))

    def set_my_commands(self, commands):
        self.commands = commands

    def infinity_polling(self, **kwargs):
        self.polled = True

    def stop_polling(self):
        self.stopped = True


def _set_pkg_module(monkeypatch: pytest.MonkeyPatch, name: str, mod: object) -> None:
    import mtproxymaxpy as pkg

    monkeypatch.setitem(sys.modules, f"mtproxymaxpy.{name}", mod)
    monkeypatch.setattr(pkg, name, mod, raising=False)


def test_basic_helpers_and_builders(monkeypatch: pytest.MonkeyPatch) -> None:
    assert telegram_bot._is_authorised(_Msg(1, "x"), "1") is True
    assert telegram_bot._is_authorised(_Msg(2, "x"), "1") is False

    b = _Bot()
    telegram_bot._send(b, "1", "hello")
    assert b.sent[-1][1] == "hello"

    class _ErrBot(_Bot):
        def send_message(self, chat_id: str, text: str, parse_mode=None):
            raise RuntimeError("boom")

    telegram_bot._send(_ErrBot(), "1", "x")
    assert telegram_bot._md("a_b") != "a_b"

    bot = _Bot()
    telegram_bot._register_bot_commands(bot)
    assert bot.commands and len(bot.commands) >= 10

    bot2 = _Bot()
    bot2.set_my_commands = lambda commands: (_ for _ in ()).throw(RuntimeError("x"))
    telegram_bot._register_bot_commands(bot2)

    _set_pkg_module(
        monkeypatch,
        "process_manager",
        SimpleNamespace(status=lambda: {"running": True, "pid": 123, "uptime_sec": 60}),
    )
    _set_pkg_module(
        monkeypatch,
        "metrics",
        SimpleNamespace(
            get_stats=lambda: {"available": True, "bytes_out": 2048, "bytes_in": 1024, "active_connections": 2}
        ),
    )
    monkeypatch.setattr(
        telegram_bot,
        "load_settings",
        lambda: SimpleNamespace(telegram_server_label="node-1", proxy_port=443),
    )
    monkeypatch.setattr(
        telegram_bot,
        "load_secrets",
        lambda: [SimpleNamespace(label="u1", enabled=True, max_conns=5, expires="2026-01-01")],
    )
    txt = telegram_bot._get_stats_text()
    assert "node\\-1" in txt
    assert "running" in txt

    _set_pkg_module(
        monkeypatch,
        "doctor",
        SimpleNamespace(
            run_full_doctor=lambda: [
                {"name": "Binary", "ok": True, "version": "1.0"},
                {"name": "Disk", "ok": False, "free_mb": 123},
            ]
        ),
    )
    h = telegram_bot._get_health_text()
    assert "Health Check" in h
    assert "Binary" in h and "Disk" in h


def test_loops(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []
    monkeypatch.setattr(telegram_bot, "_send", lambda bot, chat, text: sent.append(text))
    monkeypatch.setattr(telegram_bot, "_get_stats_text", lambda: "stats")

    class _Event:
        def __init__(self, waits, is_set_vals=None):
            self.waits = list(waits)
            self._is_set_vals = list(is_set_vals or [False] * 10)

        def wait(self, timeout=0):
            return self.waits.pop(0) if self.waits else True

        def is_set(self):
            return self._is_set_vals.pop(0) if self._is_set_vals else True

    monkeypatch.setattr(telegram_bot, "_stop_event", _Event([False, True]))
    telegram_bot._report_loop(_Bot(), "1", 1)
    assert sent == ["stats"]

    states = [False, True, True]
    _set_pkg_module(monkeypatch, "process_manager", SimpleNamespace(is_running=lambda: states.pop(0)))
    monkeypatch.setattr(telegram_bot, "_stop_event", _Event([False, False, True], [False, False, True]))
    sent2: list[str] = []
    monkeypatch.setattr(telegram_bot, "_send", lambda bot, chat, text: sent2.append(text))
    telegram_bot._health_loop(_Bot(), "1")
    assert any("recovered" in s for s in sent2)


def test_register_handlers_and_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    bot = _Bot()
    sent: list[str] = []
    monkeypatch.setattr(telegram_bot, "_send", lambda _b, _chat, text: sent.append(text))

    class _Thread:
        def __init__(self, target=None, args=(), kwargs=None, **k):
            self.target = target
            self.args = args
            self.kwargs = kwargs or {}

        def start(self):
            if self.target:
                self.target(*self.args, **self.kwargs)

    monkeypatch.setattr(telegram_bot.threading, "Thread", _Thread)

    monkeypatch.setattr(
        telegram_bot,
        "load_secrets",
        lambda: [
            SimpleNamespace(
                label="alice",
                key="a" * 32,
                enabled=True,
                max_conns=1,
                max_ips=2,
                quota_bytes=1024,
                expires="2026-01-01",
            )
        ],
    )
    monkeypatch.setattr(
        telegram_bot,
        "load_settings",
        lambda: SimpleNamespace(
            custom_ip="", proxy_domain="cloudflare.com", proxy_port=443, telegram_server_label="node"
        ),
    )
    _set_pkg_module(
        monkeypatch,
        "metrics",
        SimpleNamespace(
            get_stats=lambda *a, **k: {
                "available": True,
                "bytes_in": 1,
                "bytes_out": 2,
                "active_connections": 3,
                "total_connections": 4,
                "user_stats": {"a" * 32: {"bytes_in": 1, "bytes_out": 2, "active": 1}},
            }
        ),
    )
    _set_pkg_module(
        monkeypatch,
        "process_manager",
        SimpleNamespace(
            restart=lambda: 99,
            get_latest_version=lambda: "2.0",
            is_running=lambda: True,
            stop=lambda: None,
            download_binary=lambda **k: None,
            start=lambda public_ip="": 77,
            status=lambda: {"running": True, "pid": 1, "uptime_sec": 1},
        ),
    )
    _set_pkg_module(monkeypatch, "doctor", SimpleNamespace(run_full_doctor=lambda: [{"name": "ok", "ok": True}]))
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.secrets",
        SimpleNamespace(
            add_secret=lambda label: SimpleNamespace(label=label, key="k" * 32),
            remove_secret=lambda label: label == "alice",
            rotate_secret=lambda label: SimpleNamespace(label=label, key="z" * 32),
            enable_secret=lambda label: None,
            disable_secret=lambda label: None,
            set_secret_limits=lambda label, **kw: None,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.upstreams",
        SimpleNamespace(
            load_upstreams=lambda: [
                SimpleNamespace(name="up1", type="socks5", addr="1.1.1.1:1080", weight=10, enabled=True)
            ]
        ),
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.validation", SimpleNamespace(parse_human_bytes=lambda x: 1024))
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.network", SimpleNamespace(get_public_ip=lambda: "8.8.8.8"))
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.utils.proxy_link",
        SimpleNamespace(
            build_proxy_links=lambda *a, **k: ("tg://x", "https://x"), qr_api_url=lambda x: "https://qr.example"
        ),
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.constants", SimpleNamespace(TELEMT_VERSION="1.0"))

    telegram_bot._register_handlers(bot, "1")

    # unauthorised ignored
    bot.handlers["status"](_Msg(2, "/status"))
    assert sent == []

    bot.handlers["status"](_Msg(1, "/status"))
    bot.handlers["users"](_Msg(1, "/users"))
    bot.handlers["restart"](_Msg(1, "/restart"))
    bot.handlers["mp_health"](_Msg(1, "/mp_health"))
    bot.handlers["mp_secrets"](_Msg(1, "/mp_secrets"))
    bot.handlers["mp_link"](_Msg(1, "/mp_link alice"))
    bot.handlers["mp_add"](_Msg(1, "/mp_add bob"))
    bot.handlers["mp_remove"](_Msg(1, "/mp_remove alice"))
    bot.handlers["mp_rotate"](_Msg(1, "/mp_rotate alice"))
    bot.handlers["mp_enable"](_Msg(1, "/mp_enable alice"))
    bot.handlers["mp_disable"](_Msg(1, "/mp_disable alice"))
    bot.handlers["mp_traffic"](_Msg(1, "/mp_traffic"))
    bot.handlers["mp_update"](_Msg(1, "/mp_update"))
    bot.handlers["mp_limits"](_Msg(1, "/mp_limits alice"))
    bot.handlers["mp_setlimit"](_Msg(1, "/mp_setlimit alice conns 5"))
    bot.handlers["mp_setlimit"](_Msg(1, "/mp_setlimit alice ips 5"))
    bot.handlers["mp_setlimit"](_Msg(1, "/mp_setlimit alice quota 1G"))
    bot.handlers["mp_setlimit"](_Msg(1, "/mp_setlimit alice expires 2030-01-01"))
    bot.handlers["mp_setlimit"](_Msg(1, "/mp_setlimit alice wrong 1"))
    bot.handlers["mp_upstreams"](_Msg(1, "/mp_upstreams"))
    bot.handlers["mp_help"](_Msg(1, "/mp_help"))
    assert any("Traffic" in s or "Users" in s for s in sent)

    # usage / error branches
    sent.clear()
    bot.handlers["mp_add"](_Msg(1, "/mp_add"))
    bot.handlers["mp_remove"](_Msg(1, "/mp_remove"))
    bot.handlers["mp_rotate"](_Msg(1, "/mp_rotate"))
    bot.handlers["mp_enable"](_Msg(1, "/mp_enable"))
    bot.handlers["mp_disable"](_Msg(1, "/mp_disable"))
    bot.handlers["mp_limits"](_Msg(1, "/mp_limits"))
    bot.handlers["mp_setlimit"](_Msg(1, "/mp_setlimit"))
    assert any("Usage" in s for s in sent)

    # not found branches
    monkeypatch.setattr(telegram_bot, "load_secrets", lambda: [])
    sent.clear()
    bot.handlers["users"](_Msg(1, "/users"))
    bot.handlers["mp_link"](_Msg(1, "/mp_link"))
    bot.handlers["mp_limits"](_Msg(1, "/mp_limits alice"))
    assert any("not found" in s.lower() or "No users" in s for s in sent)

    # metrics unavailable
    _set_pkg_module(
        monkeypatch, "metrics", SimpleNamespace(get_stats=lambda *a, **k: {"available": False, "error": "x"})
    )
    sent.clear()
    bot.handlers["mp_traffic"](_Msg(1, "/mp_traffic"))
    assert any("unavailable" in s.lower() for s in sent)

    # update no-op when already latest
    _set_pkg_module(
        monkeypatch,
        "process_manager",
        SimpleNamespace(
            get_latest_version=lambda: "1.0",
            is_running=lambda: False,
            stop=lambda: None,
            download_binary=lambda **k: None,
            start=lambda public_ip="": 1,
        ),
    )
    sent.clear()
    bot.handlers["mp_update"](_Msg(1, "/mp_update"))
    assert any("Already on latest" in s for s in sent)


def test_start_stop_send_alert_and_startup_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"handlers": 0, "commands": 0, "startup": 0, "report": 0, "health": 0}
    monkeypatch.setattr(
        telegram_bot, "_register_handlers", lambda bot, chat: calls.__setitem__("handlers", calls["handlers"] + 1)
    )
    monkeypatch.setattr(
        telegram_bot, "_register_bot_commands", lambda bot: calls.__setitem__("commands", calls["commands"] + 1)
    )
    monkeypatch.setattr(
        telegram_bot, "_send_startup_notification", lambda bot, chat: calls.__setitem__("startup", calls["startup"] + 1)
    )
    monkeypatch.setattr(
        telegram_bot, "_report_loop", lambda bot, chat, interval: calls.__setitem__("report", calls["report"] + 1)
    )
    monkeypatch.setattr(
        telegram_bot, "_health_loop", lambda bot, chat: calls.__setitem__("health", calls["health"] + 1)
    )
    monkeypatch.setattr(telegram_bot, "_stop_event", SimpleNamespace(clear=lambda: None, set=lambda: None))

    class _Thread:
        def __init__(self, target=None, args=(), kwargs=None, **k):
            self.target = target
            self.args = args
            self.kwargs = kwargs or {}

        def start(self):
            # Do not execute polling target; execute worker helpers to cover branches.
            if self.target in (
                telegram_bot._send_startup_notification,
                telegram_bot._report_loop,
                telegram_bot._health_loop,
            ):
                self.target(*self.args, **self.kwargs)

    monkeypatch.setattr(telegram_bot.threading, "Thread", _Thread)
    monkeypatch.setattr(telegram_bot.telebot, "TeleBot", lambda token, parse_mode=None: _Bot())

    # disabled / missing token / missing chat id
    monkeypatch.setattr(
        telegram_bot,
        "load_settings",
        lambda: SimpleNamespace(
            telegram_enabled=False,
            telegram_bot_token="t",
            telegram_chat_id="1",
            telegram_interval=1,
            telegram_alerts_enabled=True,
        ),
    )
    telegram_bot.start()
    monkeypatch.setattr(
        telegram_bot,
        "load_settings",
        lambda: SimpleNamespace(
            telegram_enabled=True,
            telegram_bot_token="",
            telegram_chat_id="1",
            telegram_interval=1,
            telegram_alerts_enabled=True,
        ),
    )
    telegram_bot.start()
    monkeypatch.setattr(
        telegram_bot,
        "load_settings",
        lambda: SimpleNamespace(
            telegram_enabled=True,
            telegram_bot_token="t",
            telegram_chat_id="",
            telegram_interval=1,
            telegram_alerts_enabled=True,
        ),
    )
    telegram_bot.start()

    # normal start
    monkeypatch.setattr(
        telegram_bot,
        "load_settings",
        lambda: SimpleNamespace(
            telegram_enabled=True,
            telegram_bot_token="t",
            telegram_chat_id="1",
            telegram_interval=1,
            telegram_alerts_enabled=True,
        ),
    )
    telegram_bot.start()
    assert calls["handlers"] == 1
    assert calls["commands"] == 1
    assert calls["startup"] == 1
    assert calls["report"] == 1
    assert calls["health"] == 1

    # stop + send_alert
    telegram_bot._bot_instance = _Bot()
    monkeypatch.setattr(telegram_bot, "_send", lambda b, c, t: b.send_message(c, t))
    monkeypatch.setattr(
        telegram_bot, "load_settings", lambda: SimpleNamespace(telegram_enabled=True, telegram_chat_id="1")
    )
    telegram_bot.send_alert("hello_world")
    assert telegram_bot._bot_instance.sent

    telegram_bot.stop()
    assert telegram_bot._bot_instance.stopped is True

    telegram_bot._bot_instance = None
    telegram_bot.send_alert("x")
