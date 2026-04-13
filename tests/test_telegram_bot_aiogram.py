from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from mtproxymaxpy import telegram_bot_aiogram as tga


def test_start_noop_when_aiogram_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tga,
        "load_settings",
        lambda: SimpleNamespace(
            telegram_enabled=True,
            telegram_bot_token="tok",
            telegram_chat_id="1",
            telegram_interval=1,
        ),
    )

    real_import = __import__

    def _boom_import(name, *args, **kwargs):
        if name == "aiogram":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _boom_import)

    tga.start()
    assert tga._poll_thread is None


def test_start_noop_when_telegram_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tga,
        "load_settings",
        lambda: SimpleNamespace(
            telegram_enabled=False,
            telegram_bot_token="",
            telegram_chat_id="",
            telegram_interval=1,
        ),
    )
    tga.start()


def test_build_bot_commands_contains_expected_entries() -> None:
    class _Cmd:
        def __init__(self, command: str, description: str):
            self.command = command
            self.description = description

    commands = tga._build_bot_commands(_Cmd)
    names = [c.command for c in commands]

    assert "status" in names
    assert "mp_help" in names
    assert "mp_health" in names
    assert "mp_update" in names
    assert "mp_setlimit" in names
    assert len(commands) >= 17


def test_send_alert_schedules_on_aiogram_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = []

    class _Loop:
        def call_soon_threadsafe(self, cb):
            cb()

    class _Bot:
        async def send_message(self, chat_id, text, parse_mode=None):
            sent.append((chat_id, text, parse_mode))

    monkeypatch.setattr(
        tga,
        "load_settings",
        lambda: SimpleNamespace(telegram_enabled=True, telegram_chat_id="1"),
    )
    monkeypatch.setattr(tga, "_loop", _Loop())
    monkeypatch.setattr(tga, "_bot", _Bot())
    monkeypatch.setattr(tga.asyncio, "create_task", lambda coro: asyncio.run(coro))

    tga.send_alert("alert_text")

    assert sent
    assert sent[0][0] == "1"
    assert sent[0][2] == "MarkdownV2"


def test_start_polling_disables_signal_handlers() -> None:
    calls = []

    class _Dispatcher:
        async def start_polling(self, bot, **kwargs):
            calls.append((bot, kwargs))

    bot = object()
    asyncio.run(tga._start_polling(_Dispatcher(), bot))

    assert calls
    assert calls[0][0] is bot
    assert calls[0][1]["handle_signals"] is False


def test_select_mp_link_targets_without_label_returns_all_enabled() -> None:
    secrets = [
        SimpleNamespace(label="one", enabled=True),
        SimpleNamespace(label="two", enabled=True),
        SimpleNamespace(label="three", enabled=True),
        SimpleNamespace(label="off", enabled=False),
    ]

    selected = tga._select_mp_link_targets(secrets, label=None)
    labels = [s.label for s in selected]

    assert labels == ["one", "two", "three"]


def test_select_mp_link_targets_with_label_returns_single_enabled() -> None:
    secrets = [
        SimpleNamespace(label="one", enabled=True),
        SimpleNamespace(label="two", enabled=True),
        SimpleNamespace(label="two", enabled=False),
    ]

    selected = tga._select_mp_link_targets(secrets, label="two")

    assert len(selected) == 1
    assert selected[0].label == "two"


def test_is_telegram_timeout_error_for_timeout_error() -> None:
    assert tga._is_telegram_timeout_error(TimeoutError("timed out")) is True


def test_is_telegram_timeout_error_for_telegram_network_timeout_message() -> None:
    telegram_error = type("TelegramNetworkError", (Exception,), {})
    exc = telegram_error("HTTP Client says - Request timeout error")

    assert tga._is_telegram_timeout_error(exc) is True


def test_is_telegram_timeout_error_false_for_non_timeout_error() -> None:
    assert tga._is_telegram_timeout_error(RuntimeError("bad markdown")) is False
