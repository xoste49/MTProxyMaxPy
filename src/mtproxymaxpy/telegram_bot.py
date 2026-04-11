"""Telegram bot integration via pyTelegramBotAPI.

Features
--------
- Periodic traffic reports (every N hours, configurable).
- Crash / recovery alerts from process_manager health-checks.
- Commands: /status, /users, /restart (privileged).

The bot runs in its own daemon thread and can be started/stopped
independently from the proxy process.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import telebot
from telebot.types import Message

from mtproxymaxpy.config.settings import load_settings
from mtproxymaxpy.config.secrets import load_secrets
from mtproxymaxpy.utils.formatting import escape_md, format_bytes, format_duration

logger = logging.getLogger(__name__)

_bot_instance: Optional[telebot.TeleBot] = None
_stop_event = threading.Event()
_health_thread: Optional[threading.Thread] = None
_report_thread: Optional[threading.Thread] = None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_stats_text() -> str:
    """Build a human-readable status + users summary."""
    from mtproxymaxpy import process_manager
    st = process_manager.status()
    settings = load_settings()
    secrets = load_secrets()

    running_emoji = "🟢" if st["running"] else "🔴"
    lines = [
        f"{running_emoji} *{escape_md(settings.telegram_server_label)}*",
        f"Port: `{settings.proxy_port}`",
        f"Status: `{'running' if st['running'] else 'stopped'}`",
        f"PID: `{st['pid'] or 'N/A'}`",
    ]
    if secrets:
        lines.append("")
        lines.append(f"*Users* \\({len(secrets)}\\):")
        for s in secrets:
            flag = "✅" if s.enabled else "❌"
            lines.append(f"  {flag} `{escape_md(s.label)}`")
    return "\n".join(lines)


def _send(bot: telebot.TeleBot, chat_id: str, text: str) -> None:
    try:
        bot.send_message(chat_id, text, parse_mode="MarkdownV2")
    except Exception as exc:
        logger.warning("Telegram send failed: %s", exc)


# ── Periodic reporting ─────────────────────────────────────────────────────────

def _report_loop(bot: telebot.TeleBot, chat_id: str, interval_hours: int) -> None:
    interval_sec = interval_hours * 3600
    while not _stop_event.wait(timeout=interval_sec):
        _send(bot, chat_id, _get_stats_text())


# ── Health monitor ─────────────────────────────────────────────────────────────

def _health_loop(bot: telebot.TeleBot, chat_id: str) -> None:
    from mtproxymaxpy import process_manager
    was_running: Optional[bool] = None
    while not _stop_event.is_set():
        running = process_manager.is_running()
        if was_running is not None and was_running != running:
            if running:
                _send(bot, chat_id, "🟢 MTProxyMaxPy *recovered* and is running\\.")
            else:
                _send(bot, chat_id, "🔴 MTProxyMaxPy *crashed* / stopped\\!")
        was_running = running
        _stop_event.wait(timeout=30)


# ── Bot command handlers ───────────────────────────────────────────────────────

def _register_handlers(bot: telebot.TeleBot, chat_id: str) -> None:
    @bot.message_handler(commands=["status"])
    def handle_status(msg: Message) -> None:
        if str(msg.chat.id) != chat_id:
            return
        _send(bot, chat_id, _get_stats_text())

    @bot.message_handler(commands=["users"])
    def handle_users(msg: Message) -> None:
        if str(msg.chat.id) != chat_id:
            return
        secrets = load_secrets()
        if not secrets:
            _send(bot, chat_id, "No users configured\\.")
            return
        lines = ["*Users:*"]
        for s in secrets:
            flag = "✅" if s.enabled else "❌"
            lines.append(f"  {flag} `{escape_md(s.label)}` — key: `{s.key[:8]}…`")
        _send(bot, chat_id, "\n".join(lines))

    @bot.message_handler(commands=["restart"])
    def handle_restart(msg: Message) -> None:
        if str(msg.chat.id) != chat_id:
            return
        _send(bot, chat_id, "🔄 Restarting telemt…")
        from mtproxymaxpy import process_manager
        try:
            pid = process_manager.restart()
            _send(bot, chat_id, f"✅ Restarted \\(PID `{pid}`\\)")
        except Exception as exc:
            _send(bot, chat_id, f"❌ Restart failed: `{escape_md(str(exc))}`")


# ── Public API ─────────────────────────────────────────────────────────────────

def start() -> None:
    """Start background bot threads. No-op if already running or bot not configured."""
    global _bot_instance, _health_thread, _report_thread

    settings = load_settings()
    if not settings.telegram_enabled:
        logger.debug("Telegram bot is disabled in settings.")
        return
    if not settings.telegram_bot_token:
        logger.warning("Telegram bot token not set.")
        return
    if not settings.telegram_chat_id:
        logger.warning("Telegram chat ID not set.")
        return

    _stop_event.clear()
    bot = telebot.TeleBot(settings.telegram_bot_token, parse_mode=None)
    _bot_instance = bot
    chat_id = settings.telegram_chat_id

    _register_handlers(bot, chat_id)

    # Polling thread (daemon so it doesn't block process exit)
    poll_thread = threading.Thread(
        target=lambda: bot.infinity_polling(timeout=20, long_polling_timeout=15),
        daemon=True,
        name="tg-poll",
    )
    poll_thread.start()

    # Periodic report
    _report_thread = threading.Thread(
        target=_report_loop,
        args=(bot, chat_id, settings.telegram_interval),
        daemon=True,
        name="tg-report",
    )
    _report_thread.start()

    # Health monitor
    if settings.telegram_alerts_enabled:
        _health_thread = threading.Thread(
            target=_health_loop,
            args=(bot, chat_id),
            daemon=True,
            name="tg-health",
        )
        _health_thread.start()

    logger.info("Telegram bot started.")


def stop() -> None:
    """Signal all bot threads to stop."""
    _stop_event.set()
    if _bot_instance is not None:
        try:
            _bot_instance.stop_polling()
        except Exception:
            pass
    logger.info("Telegram bot stopped.")


def send_alert(text: str) -> None:
    """Send an arbitrary alert message to the configured chat."""
    settings = load_settings()
    if not settings.telegram_enabled or not _bot_instance:
        return
    _send(_bot_instance, settings.telegram_chat_id, escape_md(text))
