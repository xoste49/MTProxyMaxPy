"""Telegram bot integration via pyTelegramBotAPI.

Features
--------
- Periodic traffic reports (every N hours, configurable).
- Crash / recovery alerts from process_manager health-checks.
- Rich command set mirroring the bash MTProxyMax bot.

Commands
--------
/status   /users    /restart
/mp_secrets  /mp_link [label]  /mp_add <label>  /mp_remove <label>
/mp_rotate <label>  /mp_enable <label>  /mp_disable <label>
/mp_health  /mp_traffic  /mp_update  /mp_limits <label>
/mp_setlimit <label> <field> <value>  /mp_upstreams  /mp_help
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import telebot
from telebot.types import BotCommand, Message

from mtproxymaxpy.config.settings import load_settings
from mtproxymaxpy.config.secrets import load_secrets
from mtproxymaxpy.telegram_messages import (
    build_help_text,
    build_mp_link_text,
    build_mp_limits_text,
    build_mp_secrets_lines,
    build_mp_traffic_text,
    build_mp_upstreams_text,
    build_users_text,
)
from mtproxymaxpy.utils.formatting import escape_md, format_bytes, format_duration

logger = logging.getLogger(__name__)

_bot_instance: Optional[telebot.TeleBot] = None
_stop_event = threading.Event()
_health_thread: Optional[threading.Thread] = None
_report_thread: Optional[threading.Thread] = None


# ── Auth guard ─────────────────────────────────────────────────────────────────


def _is_authorised(msg: Message, chat_id: str) -> bool:
    return str(msg.chat.id) == chat_id


# ── Message helpers ────────────────────────────────────────────────────────────


def _send(bot: telebot.TeleBot, chat_id: str, text: str) -> None:
    try:
        bot.send_message(chat_id, text, parse_mode="MarkdownV2")
    except Exception as exc:
        logger.warning("Telegram send failed: %s", exc)


def _send_chunked(bot: telebot.TeleBot, chat_id: str, lines: list[str], *, limit: int = 3500) -> None:
    """Send long Markdown messages in chunks to stay below Telegram size limits."""
    chunk: list[str] = []
    chunk_len = 0
    for line in lines:
        line_len = len(line) + 1
        if chunk and chunk_len + line_len > limit:
            _send(bot, chat_id, "\n".join(chunk))
            chunk = [line]
            chunk_len = line_len
        else:
            chunk.append(line)
            chunk_len += line_len
    if chunk:
        _send(bot, chat_id, "\n".join(chunk))


def _md(text: str) -> str:
    return escape_md(text)


def _register_bot_commands(bot: telebot.TeleBot) -> None:
    """Publish command list so Telegram clients show the slash-command menu."""
    commands = [
        BotCommand("status", "proxy status"),
        BotCommand("users", "list users"),
        BotCommand("restart", "restart proxy"),
        BotCommand("mp_health", "full diagnostics"),
        BotCommand("mp_secrets", "secrets with traffic stats"),
        BotCommand("mp_link", "proxy link and QR"),
        BotCommand("mp_traffic", "traffic statistics"),
        BotCommand("mp_upstreams", "list upstreams"),
        BotCommand("mp_add", "add secret"),
        BotCommand("mp_remove", "remove secret"),
        BotCommand("mp_rotate", "rotate key"),
        BotCommand("mp_enable", "enable secret"),
        BotCommand("mp_disable", "disable secret"),
        BotCommand("mp_limits", "show limits"),
        BotCommand("mp_setlimit", "set limit value"),
        BotCommand("mp_update", "update telemt binary"),
        BotCommand("mp_help", "show help"),
    ]
    try:
        bot.set_my_commands(commands)
    except Exception as exc:
        logger.warning("Failed to register Telegram commands menu: %s", exc)


# ── Status text builders ───────────────────────────────────────────────────────


def _get_stats_text() -> str:
    from mtproxymaxpy import process_manager, metrics as _metrics

    st = process_manager.status()
    settings = load_settings()
    secrets = load_secrets()

    running_emoji = "🟢" if st["running"] else "🔴"
    uptime_str = escape_md(format_duration(st["uptime_sec"])) if st.get("uptime_sec") else "?"
    lines = [
        f"{running_emoji} *{_md(settings.telegram_server_label)}*",
        f"Port: `{settings.proxy_port}`",
        f"Status: `{'running' if st['running'] else 'stopped'}`",
        f"PID: `{st['pid'] or 'N/A'}`",
        f"Uptime: `{uptime_str}`",
    ]
    mst = _metrics.get_stats()
    if mst.get("available"):
        lines += [
            f"Traffic ↑: `{_md(format_bytes(mst['bytes_out']))}`",
            f"Traffic ↓: `{_md(format_bytes(mst['bytes_in']))}`",
            f"Active conns: `{mst['active_connections']}`",
        ]
    if secrets:
        lines.append("")
        lines.append(f"*Users* \\({len(secrets)}\\):")
        for s in secrets:
            flag = "✅" if s.enabled else "❌"
            limits = []
            if s.max_conns:
                limits.append(f"conns≤{s.max_conns}")
            if s.expires:
                limits.append(f"exp:{s.expires}")
            extra = f" \\({_md(', '.join(limits))}\\)" if limits else ""
            lines.append(f"  {flag} `{_md(s.label)}`{extra}")
    return "\n".join(lines)


def _get_health_text() -> str:
    from mtproxymaxpy import doctor

    results = doctor.run_full_doctor()
    lines = ["🏥 *Health Check*", ""]
    for r in results:
        ok = r.get("ok")
        icon = "✅" if ok is True else ("❌" if ok is False else "⚠️")
        name = _md(r["name"])
        extras: list[str] = []
        if r.get("version"):
            extras.append(f"v{_md(str(r['version']))}")
        if r.get("pid"):
            extras.append(f"pid={r['pid']}")
        if r.get("free_mb") is not None:
            extras.append(f"{r['free_mb']}MB free")
        if r.get("error"):
            extras.append(_md(str(r["error"])))
        if r.get("note"):
            extras.append(_md(str(r["note"])))
        extra_str = f" — {', '.join(extras)}" if extras else ""
        lines.append(f"{icon} {name}{extra_str}")
    return "\n".join(lines)


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


def _register_handlers(bot: telebot.TeleBot, chat_id: str) -> None:  # noqa: C901

    def guard(msg: Message) -> bool:
        if not _is_authorised(msg, chat_id):
            return False
        return True

    # /status
    @bot.message_handler(commands=["status"])
    def handle_status(msg: Message) -> None:
        if not guard(msg):
            return
        _send(bot, chat_id, _get_stats_text())

    # /users
    @bot.message_handler(commands=["users"])
    def handle_users(msg: Message) -> None:
        if not guard(msg):
            return
        _send(bot, chat_id, build_users_text(load_secrets(), md=_md))

    # /restart
    @bot.message_handler(commands=["restart"])
    def handle_restart(msg: Message) -> None:
        if not guard(msg):
            return
        _send(bot, chat_id, "🔄 Restarting telemt…")
        from mtproxymaxpy import process_manager

        try:
            pid = process_manager.restart()
            _send(bot, chat_id, f"✅ Restarted \\(PID `{pid}`\\)")
        except Exception as exc:
            _send(bot, chat_id, f"❌ Restart failed: `{_md(str(exc))}`")

    # /mp_health
    @bot.message_handler(commands=["mp_health"])
    def handle_health(msg: Message) -> None:
        if not guard(msg):
            return
        _send(bot, chat_id, _get_health_text())

    # /mp_secrets
    @bot.message_handler(commands=["mp_secrets"])
    def handle_mp_secrets(msg: Message) -> None:
        if not guard(msg):
            return
        from mtproxymaxpy import metrics as _metrics

        _send(bot, chat_id, "⏳ Collecting secrets stats…")

        def _render_and_send() -> None:
            try:
                secrets = load_secrets()
                mst = _metrics.get_stats(timeout=2.0, max_age=5.0)
                lines = build_mp_secrets_lines(secrets, mst, md=_md, bytes_formatter=format_bytes)
                _send_chunked(bot, chat_id, lines)
            except Exception as exc:
                _send(bot, chat_id, f"❌ Failed to collect stats: `{_md(str(exc))}`")

        threading.Thread(target=_render_and_send, daemon=True, name="tg-mp-secrets").start()

    # /mp_link [label]
    @bot.message_handler(commands=["mp_link"])
    def handle_mp_link(msg: Message) -> None:
        if not guard(msg):
            return
        from mtproxymaxpy.config.settings import load_settings as ls
        from mtproxymaxpy.utils.network import get_public_ip
        from mtproxymaxpy.utils.proxy_link import build_proxy_links, qr_api_url

        args = msg.text.split(maxsplit=1)
        label = args[1].strip() if len(args) > 1 else None
        secrets = load_secrets()
        s = next((x for x in secrets if (not label or x.label == label) and x.enabled), None)
        if s is None:
            _send(bot, chat_id, "❌ Secret not found\\.")
            return
        settings = ls()
        srv = settings.custom_ip or get_public_ip() or "?"
        tg, web = build_proxy_links(s.key, settings.proxy_domain, srv, settings.proxy_port)
        qr_url = qr_api_url(web)
        _send(bot, chat_id, build_mp_link_text(s.label, tg, web, qr_url, md=_md))

    # /mp_add <label>
    @bot.message_handler(commands=["mp_add"])
    def handle_mp_add(msg: Message) -> None:
        if not guard(msg):
            return
        from mtproxymaxpy.config.secrets import add_secret

        args = msg.text.split(maxsplit=1)
        if len(args) < 2:
            _send(bot, chat_id, "Usage: /mp\\_add \\<label\\>")
            return
        label = args[1].strip()
        try:
            s = add_secret(label)
            _send(bot, chat_id, f"✅ Added `{_md(s.label)}`: `{_md(s.key)}`")
        except Exception as exc:
            _send(bot, chat_id, f"❌ {_md(str(exc))}")

    # /mp_remove <label>
    @bot.message_handler(commands=["mp_remove"])
    def handle_mp_remove(msg: Message) -> None:
        if not guard(msg):
            return
        from mtproxymaxpy.config.secrets import remove_secret

        args = msg.text.split(maxsplit=1)
        if len(args) < 2:
            _send(bot, chat_id, "Usage: /mp\\_remove \\<label\\>")
            return
        label = args[1].strip()
        if remove_secret(label):
            _send(bot, chat_id, f"✅ Removed `{_md(label)}`")
        else:
            _send(bot, chat_id, f"❌ Not found: `{_md(label)}`")

    # /mp_rotate <label>
    @bot.message_handler(commands=["mp_rotate"])
    def handle_mp_rotate(msg: Message) -> None:
        if not guard(msg):
            return
        from mtproxymaxpy.config.secrets import rotate_secret

        args = msg.text.split(maxsplit=1)
        if len(args) < 2:
            _send(bot, chat_id, "Usage: /mp\\_rotate \\<label\\>")
            return
        label = args[1].strip()
        try:
            s = rotate_secret(label)
            _send(bot, chat_id, f"✅ Rotated `{_md(s.label)}`\\. New key: `{_md(s.key)}`")
        except KeyError as exc:
            _send(bot, chat_id, f"❌ {_md(str(exc))}")

    # /mp_enable <label>
    @bot.message_handler(commands=["mp_enable"])
    def handle_mp_enable(msg: Message) -> None:
        if not guard(msg):
            return
        from mtproxymaxpy.config.secrets import enable_secret

        args = msg.text.split(maxsplit=1)
        if len(args) < 2:
            _send(bot, chat_id, "Usage: /mp\\_enable \\<label\\>")
            return
        try:
            enable_secret(args[1].strip())
            _send(bot, chat_id, f"✅ Enabled `{_md(args[1].strip())}`")
        except Exception as exc:
            _send(bot, chat_id, f"❌ {_md(str(exc))}")

    # /mp_disable <label>
    @bot.message_handler(commands=["mp_disable"])
    def handle_mp_disable(msg: Message) -> None:
        if not guard(msg):
            return
        from mtproxymaxpy.config.secrets import disable_secret

        args = msg.text.split(maxsplit=1)
        if len(args) < 2:
            _send(bot, chat_id, "Usage: /mp\\_disable \\<label\\>")
            return
        try:
            disable_secret(args[1].strip())
            _send(bot, chat_id, f"✅ Disabled `{_md(args[1].strip())}`")
        except Exception as exc:
            _send(bot, chat_id, f"❌ {_md(str(exc))}")

    # /mp_traffic
    @bot.message_handler(commands=["mp_traffic"])
    def handle_mp_traffic(msg: Message) -> None:
        if not guard(msg):
            return
        from mtproxymaxpy import metrics as _metrics

        mst = _metrics.get_stats()
        if not mst.get("available"):
            _send(bot, chat_id, "❌ Metrics unavailable\\.")
            return
        _send(bot, chat_id, build_mp_traffic_text(mst, md=_md, bytes_formatter=format_bytes))

    # /mp_update
    @bot.message_handler(commands=["mp_update"])
    def handle_mp_update(msg: Message) -> None:
        if not guard(msg):
            return
        from mtproxymaxpy import process_manager
        from mtproxymaxpy.constants import TELEMT_VERSION

        _send(bot, chat_id, "🔍 Checking for updates…")
        try:
            latest = process_manager.get_latest_version()
            if latest == TELEMT_VERSION:
                _send(bot, chat_id, f"✅ Already on latest: `{_md(TELEMT_VERSION)}`")
                return
            _send(bot, chat_id, f"⬇️ Updating `{_md(TELEMT_VERSION)}` → `{_md(latest)}`…")
            was_running = process_manager.is_running()
            if was_running:
                process_manager.stop()
            process_manager.download_binary(version=latest, force=True)
            if was_running:
                from mtproxymaxpy.utils.network import get_public_ip

                pid = process_manager.start(public_ip=get_public_ip() or "")
                _send(bot, chat_id, f"✅ Updated and restarted \\(PID `{pid}`\\)")
            else:
                _send(bot, chat_id, "✅ Binary updated\\.")
        except Exception as exc:
            _send(bot, chat_id, f"❌ Update failed: `{_md(str(exc))}`")

    # /mp_limits <label>
    @bot.message_handler(commands=["mp_limits"])
    def handle_mp_limits(msg: Message) -> None:
        if not guard(msg):
            return
        args = msg.text.split(maxsplit=1)
        if len(args) < 2:
            _send(bot, chat_id, "Usage: /mp\\_limits \\<label\\>")
            return
        label = args[1].strip()
        secrets = load_secrets()
        s = next((x for x in secrets if x.label == label), None)
        if s is None:
            _send(bot, chat_id, f"❌ Not found: `{_md(label)}`")
            return
        _send(bot, chat_id, build_mp_limits_text(s, md=_md, bytes_formatter=format_bytes))

    # /mp_setlimit <label> <field> <value>
    @bot.message_handler(commands=["mp_setlimit"])
    def handle_mp_setlimit(msg: Message) -> None:
        if not guard(msg):
            return
        from mtproxymaxpy.config.secrets import set_secret_limits
        from mtproxymaxpy.utils.validation import parse_human_bytes

        parts = msg.text.split(maxsplit=3)
        if len(parts) < 4:
            _send(bot, chat_id, "Usage: /mp\\_setlimit \\<label\\> \\<conns\\|ips\\|quota\\|expires\\> \\<value\\>")
            return
        _, label, field, value = parts
        try:
            kwargs: dict = {}
            if field == "conns":
                kwargs["max_conns"] = int(value)
            elif field == "ips":
                kwargs["max_ips"] = int(value)
            elif field == "quota":
                kwargs["quota_bytes"] = parse_human_bytes(value)
            elif field == "expires":
                kwargs["expires"] = value
            else:
                _send(bot, chat_id, f"❌ Unknown field `{_md(field)}`")
                return
            set_secret_limits(label, **kwargs)
            _send(bot, chat_id, f"✅ Updated `{_md(field)}` for `{_md(label)}`")
        except Exception as exc:
            _send(bot, chat_id, f"❌ {_md(str(exc))}")

    # /mp_upstreams
    @bot.message_handler(commands=["mp_upstreams"])
    def handle_mp_upstreams(msg: Message) -> None:
        if not guard(msg):
            return
        from mtproxymaxpy.config.upstreams import load_upstreams

        ups = load_upstreams()
        _send(bot, chat_id, build_mp_upstreams_text(ups, md=_md))

    # /mp_help
    @bot.message_handler(commands=["mp_help", "help", "start"])
    def handle_mp_help(msg: Message) -> None:
        if not guard(msg):
            return
        _send(bot, chat_id, build_help_text())


# ── Startup notification ───────────────────────────────────────────────────────


def _send_startup_notification(bot: telebot.TeleBot, chat_id: str) -> None:
    """Send a startup notification with proxy links."""
    from mtproxymaxpy.config.settings import load_settings as ls
    from mtproxymaxpy.utils.network import get_public_ip
    from mtproxymaxpy.utils.proxy_link import build_proxy_links

    try:
        settings = ls()
        srv = settings.custom_ip or get_public_ip() or "?"
        secrets = load_secrets()
        enabled = [s for s in secrets if s.enabled]

        lines = [f"🚀 *{_md(settings.telegram_server_label)}* started", ""]
        if not enabled:
            lines.append("No enabled secrets\\.")
            _send(bot, chat_id, "\n".join(lines))
            return
        if srv == "?":
            lines.append("Could not detect server IP/domain for links\\.")
            _send(bot, chat_id, "\n".join(lines))
            return

        for s in enabled:
            _, web = build_proxy_links(s.key, settings.proxy_domain, srv, settings.proxy_port)
            lines.append(f"🏷 *{_md(s.label)}*")
            lines.append(f"`{_md(web)}`")
            lines.append("")

        lines.append(f"Domain: `{_md(settings.proxy_domain)}`")
        _send_chunked(bot, chat_id, lines)
    except Exception as exc:
        logger.debug("Startup notification failed: %s", exc)


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
    _register_bot_commands(bot)

    # Polling thread
    poll_thread = threading.Thread(
        target=lambda: bot.infinity_polling(timeout=20, long_polling_timeout=15),
        daemon=True,
        name="tg-poll",
    )
    poll_thread.start()

    # Startup notification
    threading.Thread(
        target=_send_startup_notification,
        args=(bot, chat_id),
        daemon=True,
        name="tg-startup",
    ).start()

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
