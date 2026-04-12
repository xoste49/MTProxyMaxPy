"""Unit tests for Telegram bot helpers and startup notifications."""

from __future__ import annotations

from mtproxymaxpy.config.secrets import Secret
from mtproxymaxpy.config.settings import Settings
from mtproxymaxpy import telegram_bot


class _DummyBot:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send_message(self, chat_id: str, text: str, parse_mode: str) -> None:
        self.messages.append(text)


def test_send_chunked_splits_long_messages() -> None:
    bot = _DummyBot()
    lines = ["x" * 20, "y" * 20, "z" * 20]

    telegram_bot._send_chunked(bot, "1", lines, limit=45)

    assert len(bot.messages) == 2
    assert bot.messages[0] == "\n".join(lines[:2])
    assert bot.messages[1] == lines[2]


def test_startup_notification_lists_all_enabled_secrets(monkeypatch) -> None:
    sent: list[tuple[str, list[str]]] = []
    calls: list[tuple[str, str, str, int]] = []

    settings = Settings(
        telegram_server_label="node-1",
        custom_ip="198.51.100.10",
        proxy_domain="example.com",
        proxy_port=443,
    )
    secrets = [
        Secret(label="alpha", key="a" * 32, enabled=True),
        Secret(label="beta", key="b" * 32, enabled=True),
        Secret(label="disabled", key="c" * 32, enabled=False),
    ]

    monkeypatch.setattr(telegram_bot, "load_secrets", lambda: secrets)
    monkeypatch.setattr(telegram_bot, "_send", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        telegram_bot,
        "_send_chunked",
        lambda _bot, chat_id, lines, limit=3500: sent.append((chat_id, list(lines))),
    )

    import mtproxymaxpy.config.settings as settings_module
    import mtproxymaxpy.utils.proxy_link as proxy_link_module

    monkeypatch.setattr(settings_module, "load_settings", lambda: settings)

    def _fake_build_proxy_links(key: str, domain: str, srv: str, port: int):
        calls.append((key, domain, srv, port))
        return "tg://proxy", f"https://t.me/proxy?server={srv}&secret={key}"

    monkeypatch.setattr(proxy_link_module, "build_proxy_links", _fake_build_proxy_links)

    telegram_bot._send_startup_notification(_DummyBot(), "777")

    assert len(sent) == 1
    chat_id, lines = sent[0]
    message = "\n".join(lines)
    assert chat_id == "777"
    assert "*node\\-1*" in message
    assert "*alpha*" in message
    assert "*beta*" in message
    assert "*disabled*" not in message
    assert "Domain: `example\\.com`" in message
    assert len(calls) == 2
    assert all(call[1:] == ("example.com", "198.51.100.10", 443) for call in calls)


def test_startup_notification_handles_no_enabled_secrets(monkeypatch) -> None:
    sent: list[str] = []

    settings = Settings(telegram_server_label="node", custom_ip="203.0.113.5")

    monkeypatch.setattr(telegram_bot, "load_secrets", lambda: [Secret(label="off", enabled=False, key="a" * 32)])
    monkeypatch.setattr(telegram_bot, "_send_chunked", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(telegram_bot, "_send", lambda _bot, _chat, text: sent.append(text))

    import mtproxymaxpy.config.settings as settings_module

    monkeypatch.setattr(settings_module, "load_settings", lambda: settings)

    telegram_bot._send_startup_notification(_DummyBot(), "1")

    assert len(sent) == 1
    assert "No enabled secrets\\." in sent[0]


def test_startup_notification_handles_missing_public_ip(monkeypatch) -> None:
    sent: list[str] = []

    settings = Settings(telegram_server_label="node", custom_ip="")

    monkeypatch.setattr(telegram_bot, "load_secrets", lambda: [Secret(label="on", enabled=True, key="a" * 32)])
    monkeypatch.setattr(telegram_bot, "_send_chunked", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(telegram_bot, "_send", lambda _bot, _chat, text: sent.append(text))

    import mtproxymaxpy.config.settings as settings_module
    import mtproxymaxpy.utils.network as network_module

    monkeypatch.setattr(settings_module, "load_settings", lambda: settings)
    monkeypatch.setattr(network_module, "get_public_ip", lambda: None)

    telegram_bot._send_startup_notification(_DummyBot(), "1")

    assert len(sent) == 1
    assert "Could not detect server IP/domain for links\\." in sent[0]
