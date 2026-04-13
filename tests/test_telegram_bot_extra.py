from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from mtproxymaxpy import telegram_bot


class _Bot:
    def __init__(self):
        self.sent = []

    def send_message(self, chat_id: str, text: str, parse_mode=None):
        self.sent.append((chat_id, text, parse_mode))

    def stop_polling(self):
        return None


def _set_pkg_module(monkeypatch: pytest.MonkeyPatch, name: str, mod: object) -> None:
    import mtproxymaxpy as pkg

    monkeypatch.setitem(sys.modules, f"mtproxymaxpy.{name}", mod)
    monkeypatch.setattr(pkg, name, mod, raising=False)


def test_send_chunked_splits_long_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    out = []
    monkeypatch.setattr(telegram_bot, "_send", lambda b, chat, text: out.append(text))
    lines = ["x" * 20, "y" * 20, "z" * 20]
    telegram_bot._send_chunked(_Bot(), "1", lines, limit=30)
    assert len(out) == 3


def test_send_startup_notification_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = []
    monkeypatch.setattr(telegram_bot, "_send", lambda b, chat, text: sent.append(text))
    monkeypatch.setattr(telegram_bot, "_send_chunked", lambda b, chat, lines, limit=3500: sent.append("\n".join(lines)))

    # no enabled secrets
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(
            load_settings=lambda: SimpleNamespace(
                custom_ip="", proxy_domain="cf.com", proxy_port=443, telegram_server_label="node"
            )
        ),
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.network", SimpleNamespace(get_public_ip=lambda: "1.2.3.4"))
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.utils.proxy_link",
        SimpleNamespace(build_proxy_links=lambda *a, **k: ("tg://x", "https://x")),
    )
    monkeypatch.setattr(telegram_bot, "load_secrets", lambda: [])
    telegram_bot._send_startup_notification(_Bot(), "1")
    assert any("No enabled secrets" in s for s in sent)

    # unknown server path
    sent.clear()
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.network", SimpleNamespace(get_public_ip=lambda: ""))
    monkeypatch.setattr(telegram_bot, "load_secrets", lambda: [SimpleNamespace(enabled=True, label="u1", key="a" * 32)])
    telegram_bot._send_startup_notification(_Bot(), "1")
    assert any("Could not detect" in s for s in sent)

    # success with enabled secrets
    sent.clear()
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.network", SimpleNamespace(get_public_ip=lambda: "2.2.2.2"))
    telegram_bot._send_startup_notification(_Bot(), "1")
    assert any("started" in s for s in sent)

    # exception swallowed/logged path
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(load_settings=lambda: (_ for _ in ()).throw(RuntimeError("bad"))),
    )
    telegram_bot._send_startup_notification(_Bot(), "1")


def test_start_without_health_thread_and_stop_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"health": 0}
    monkeypatch.setattr(telegram_bot, "_register_handlers", lambda *a, **k: None)
    monkeypatch.setattr(telegram_bot, "_register_bot_commands", lambda *a, **k: None)
    monkeypatch.setattr(telegram_bot, "_send_startup_notification", lambda *a, **k: None)
    monkeypatch.setattr(telegram_bot, "_report_loop", lambda *a, **k: None)
    monkeypatch.setattr(telegram_bot, "_health_loop", lambda *a, **k: calls.__setitem__("health", calls["health"] + 1))
    monkeypatch.setattr(telegram_bot, "_stop_event", SimpleNamespace(clear=lambda: None, set=lambda: None))

    class _Thread:
        def __init__(self, target=None, args=(), kwargs=None, **k):
            self.target = target
            self.args = args
            self.kwargs = kwargs or {}

        def start(self):
            if self.target in (
                telegram_bot._send_startup_notification,
                telegram_bot._report_loop,
                telegram_bot._health_loop,
            ):
                self.target(*self.args, **self.kwargs)

    monkeypatch.setattr(telegram_bot.threading, "Thread", _Thread)
    monkeypatch.setattr(telegram_bot.telebot, "TeleBot", lambda token, parse_mode=None: _Bot())

    # alerts disabled -> health thread should not run
    monkeypatch.setattr(
        telegram_bot,
        "load_settings",
        lambda: SimpleNamespace(
            telegram_enabled=True,
            telegram_bot_token="t",
            telegram_chat_id="1",
            telegram_interval=1,
            telegram_alerts_enabled=False,
        ),
    )
    telegram_bot.start()
    assert calls["health"] == 0

    class _ErrBot(_Bot):
        def stop_polling(self):
            raise RuntimeError("x")

    telegram_bot._bot_instance = _ErrBot()
    telegram_bot.stop()


def test_mp_secrets_worker_failure_and_update_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = []
    monkeypatch.setattr(telegram_bot, "_send", lambda b, chat, text: sent.append(text))
    monkeypatch.setattr(telegram_bot, "_send_chunked", lambda b, chat, lines, limit=3500: sent.append("\n".join(lines)))

    class _Msg:
        def __init__(self, text: str):
            self.chat = SimpleNamespace(id=1)
            self.text = text

    class _HBot:
        def __init__(self):
            self.handlers = {}

        def message_handler(self, commands=None):
            def _d(fn):
                for c in commands or []:
                    self.handlers[c] = fn
                return fn

            return _d

    bot = _HBot()
    monkeypatch.setattr(
        telegram_bot,
        "load_settings",
        lambda: SimpleNamespace(custom_ip="", proxy_domain="cf.com", proxy_port=443, telegram_server_label="node"),
    )
    monkeypatch.setattr(telegram_bot, "load_secrets", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    _set_pkg_module(monkeypatch, "metrics", SimpleNamespace(get_stats=lambda *a, **k: {"available": True}))

    class _Thread:
        def __init__(self, target=None, args=(), kwargs=None, **k):
            self.target = target
            self.args = args
            self.kwargs = kwargs or {}

        def start(self):
            if self.target:
                self.target(*self.args, **self.kwargs)

    monkeypatch.setattr(telegram_bot.threading, "Thread", _Thread)
    telegram_bot._register_handlers(bot, "1")
    bot.handlers["mp_secrets"](_Msg("/mp_secrets"))
    assert any("Failed to collect stats" in s for s in sent)

    sent.clear()
    _set_pkg_module(
        monkeypatch,
        "process_manager",
        SimpleNamespace(
            get_latest_version=lambda: "2.0",
            is_running=lambda: True,
            stop=lambda: (_ for _ in ()).throw(RuntimeError("stop failed")),
            download_binary=lambda **k: None,
            start=lambda public_ip="": 1,
        ),
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.constants", SimpleNamespace(TELEMT_VERSION="1.0"))
    bot.handlers["mp_update"](_Msg("/mp_update"))
    assert any("Update failed" in s for s in sent)


def test_mp_secrets_escapes_equals_for_markdown_v2(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = []
    chunked = []
    monkeypatch.setattr(telegram_bot, "_send", lambda b, chat, text: sent.append(text))
    monkeypatch.setattr(
        telegram_bot, "_send_chunked", lambda b, chat, lines, limit=3500: chunked.append("\n".join(lines))
    )

    class _Msg:
        def __init__(self, text: str):
            self.chat = SimpleNamespace(id=1)
            self.text = text

    class _HBot:
        def __init__(self):
            self.handlers = {}

        def message_handler(self, commands=None):
            def _d(fn):
                for c in commands or []:
                    self.handlers[c] = fn
                return fn

            return _d

    bot = _HBot()
    monkeypatch.setattr(
        telegram_bot,
        "load_settings",
        lambda: SimpleNamespace(custom_ip="", proxy_domain="cf.com", proxy_port=443, telegram_server_label="node"),
    )
    monkeypatch.setattr(
        telegram_bot,
        "load_secrets",
        lambda: [SimpleNamespace(label="alice", key="a" * 32, enabled=True)],
    )
    _set_pkg_module(
        monkeypatch,
        "metrics",
        SimpleNamespace(
            get_stats=lambda *a, **k: {
                "available": True,
                "user_stats": {"a" * 32: {"bytes_in": 1024, "bytes_out": 2048, "active": 3}},
            }
        ),
    )

    class _Thread:
        def __init__(self, target=None, args=(), kwargs=None, **k):
            self.target = target
            self.args = args
            self.kwargs = kwargs or {}

        def start(self):
            if self.target:
                self.target(*self.args, **self.kwargs)

    monkeypatch.setattr(telegram_bot.threading, "Thread", _Thread)

    telegram_bot._register_handlers(bot, "1")
    bot.handlers["mp_secrets"](_Msg("/mp_secrets"))

    assert any("Collecting secrets stats" in s for s in sent)
    assert any("conns\\=" in payload for payload in chunked)


def test_more_handler_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = []
    monkeypatch.setattr(telegram_bot, "_send", lambda b, chat, text: sent.append(text))

    class _Msg:
        def __init__(self, text: str):
            self.chat = SimpleNamespace(id=1)
            self.text = text

    class _HBot:
        def __init__(self):
            self.handlers = {}

        def message_handler(self, commands=None):
            def _d(fn):
                for c in commands or []:
                    self.handlers[c] = fn
                return fn

            return _d

    bot = _HBot()
    monkeypatch.setattr(
        telegram_bot,
        "load_settings",
        lambda: SimpleNamespace(custom_ip="", proxy_domain="cf.com", proxy_port=443, telegram_server_label="node"),
    )
    monkeypatch.setattr(
        telegram_bot,
        "load_secrets",
        lambda: [
            SimpleNamespace(
                label="alice", key="a" * 32, enabled=True, max_conns=0, max_ips=0, quota_bytes=0, expires=""
            )
        ],
    )
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.secrets",
        SimpleNamespace(
            add_secret=lambda label: (_ for _ in ()).throw(RuntimeError("add bad")),
            remove_secret=lambda label: False,
            rotate_secret=lambda label: (_ for _ in ()).throw(KeyError("no")),
            enable_secret=lambda label: (_ for _ in ()).throw(RuntimeError("en bad")),
            disable_secret=lambda label: (_ for _ in ()).throw(RuntimeError("dis bad")),
            set_secret_limits=lambda label, **kw: (_ for _ in ()).throw(RuntimeError("lim bad")),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.utils.validation",
        SimpleNamespace(parse_human_bytes=lambda x: (_ for _ in ()).throw(ValueError("bad"))),
    )
    _set_pkg_module(
        monkeypatch,
        "metrics",
        SimpleNamespace(
            get_stats=lambda: {
                "available": True,
                "bytes_in": 1,
                "bytes_out": 2,
                "active_connections": 1,
                "total_connections": 1,
            }
        ),
    )
    _set_pkg_module(
        monkeypatch,
        "process_manager",
        SimpleNamespace(
            get_latest_version=lambda: "2.0",
            is_running=lambda: False,
            stop=lambda: None,
            download_binary=lambda **k: None,
            start=lambda public_ip="": 1,
        ),
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.constants", SimpleNamespace(TELEMT_VERSION="1.0"))

    telegram_bot._register_handlers(bot, "1")
    bot.handlers["mp_add"](_Msg("/mp_add bob"))
    bot.handlers["mp_remove"](_Msg("/mp_remove bob"))
    bot.handlers["mp_rotate"](_Msg("/mp_rotate bob"))
    bot.handlers["mp_enable"](_Msg("/mp_enable bob"))
    bot.handlers["mp_disable"](_Msg("/mp_disable bob"))
    bot.handlers["mp_setlimit"](_Msg("/mp_setlimit bob quota 1G"))
    bot.handlers["mp_setlimit"](_Msg("/mp_setlimit bob conns 1"))
    bot.handlers["mp_update"](_Msg("/mp_update"))

    assert any("add bad" in s for s in sent)
    assert any("Not found" in s for s in sent)
    assert any("en bad" in s for s in sent)


def test_upstreams_and_help_guard_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = []
    monkeypatch.setattr(telegram_bot, "_send", lambda b, chat, text: sent.append(text))

    class _Msg:
        def __init__(self, chat_id: int, text: str):
            self.chat = SimpleNamespace(id=chat_id)
            self.text = text

    class _HBot:
        def __init__(self):
            self.handlers = {}

        def message_handler(self, commands=None):
            def _d(fn):
                for c in commands or []:
                    self.handlers[c] = fn
                return fn

            return _d

    bot = _HBot()
    monkeypatch.setattr(
        telegram_bot,
        "load_settings",
        lambda: SimpleNamespace(custom_ip="", proxy_domain="cf.com", proxy_port=443, telegram_server_label="node"),
    )
    monkeypatch.setattr(telegram_bot, "load_secrets", lambda: [])
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.config.upstreams", SimpleNamespace(load_upstreams=lambda: []))
    telegram_bot._register_handlers(bot, "1")

    # guard false for mp_upstreams and mp_help
    bot.handlers["mp_upstreams"](_Msg(2, "/mp_upstreams"))
    bot.handlers["mp_help"](_Msg(2, "/mp_help"))
    assert sent == []

    # no upstreams branch
    bot.handlers["mp_upstreams"](_Msg(1, "/mp_upstreams"))
    assert any("No upstreams configured" in s for s in sent)


def test_more_unauthorised_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = []
    monkeypatch.setattr(telegram_bot, "_send", lambda b, chat, text: sent.append(text))

    class _Msg:
        def __init__(self, chat_id: int, text: str):
            self.chat = SimpleNamespace(id=chat_id)
            self.text = text

    class _HBot:
        def __init__(self):
            self.handlers = {}

        def message_handler(self, commands=None):
            def _d(fn):
                for c in commands or []:
                    self.handlers[c] = fn
                return fn

            return _d

    bot = _HBot()
    monkeypatch.setattr(
        telegram_bot,
        "load_settings",
        lambda: SimpleNamespace(custom_ip="", proxy_domain="cf.com", proxy_port=443, telegram_server_label="node"),
    )
    monkeypatch.setattr(telegram_bot, "load_secrets", lambda: [])
    telegram_bot._register_handlers(bot, "1")

    bot.handlers["mp_update"](_Msg(2, "/mp_update"))
    bot.handlers["mp_limits"](_Msg(2, "/mp_limits x"))
    bot.handlers["mp_setlimit"](_Msg(2, "/mp_setlimit x conns 1"))
    assert sent == []
