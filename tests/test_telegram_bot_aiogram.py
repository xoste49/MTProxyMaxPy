from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from mtproxymaxpy import telegram_bot_aiogram as tga


class _Legacy:
    def __init__(self) -> None:
        self.calls = {"start": 0, "stop": 0, "alert": 0}

    def start(self) -> None:
        self.calls["start"] += 1

    def stop(self) -> None:
        self.calls["stop"] += 1

    def send_alert(self, text: str) -> None:
        self.calls["alert"] += 1


def test_start_fallbacks_to_legacy_when_aiogram_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    legacy = _Legacy()
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
    monkeypatch.setattr(tga, "_start_legacy", lambda reason: legacy.start())

    real_import = __import__

    def _boom_import(name, *args, **kwargs):
        if name == "aiogram":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _boom_import)

    tga.start()
    assert legacy.calls["start"] == 1


def test_stop_and_send_alert_delegate_in_legacy_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    legacy = _Legacy()
    monkeypatch.setattr(tga, "_using_legacy", True)
    monkeypatch.setattr(tga, "_legacy_module", legacy)

    tga.stop()
    tga.send_alert("hello")

    assert legacy.calls["stop"] == 1
    assert legacy.calls["alert"] == 1


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
    monkeypatch.setattr(tga, "_start_legacy", lambda reason: (_ for _ in ()).throw(RuntimeError("should not call")))

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
    monkeypatch.setattr(tga, "_using_legacy", False)
    monkeypatch.setattr(tga, "_legacy_module", None)
    monkeypatch.setattr(tga, "_loop", _Loop())
    monkeypatch.setattr(tga, "_bot", _Bot())
    monkeypatch.setattr(tga.asyncio, "create_task", lambda coro: asyncio.run(coro))

    tga.send_alert("alert_text")

    assert sent
    assert sent[0][0] == "1"
    assert sent[0][2] == "MarkdownV2"
