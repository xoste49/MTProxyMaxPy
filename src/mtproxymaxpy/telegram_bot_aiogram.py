"""Aiogram Telegram bot backend."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from mtproxymaxpy.config.secrets import load_secrets
from mtproxymaxpy.config.settings import load_settings
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

_poll_thread: threading.Thread | None = None
_loop: asyncio.AbstractEventLoop | None = None
_bot: Any = None
_dispatcher: Any = None
_started_event = threading.Event()

_COMMAND_SPECS: tuple[tuple[str, str], ...] = (
    ("status", "proxy status"),
    ("users", "list users"),
    ("restart", "restart proxy"),
    ("mp_help", "show help"),
    ("mp_health", "full diagnostics"),
    ("mp_traffic", "traffic statistics"),
    ("mp_secrets", "secrets with traffic stats"),
    ("mp_limits", "show limits"),
    ("mp_setlimit", "set limit value"),
    ("mp_upstreams", "list upstreams"),
    ("mp_link", "proxy link and QR"),
    ("mp_add", "add secret"),
    ("mp_remove", "remove secret"),
    ("mp_rotate", "rotate key"),
    ("mp_enable", "enable secret"),
    ("mp_disable", "disable secret"),
    ("mp_update", "update telemt binary"),
)


def _md(text: str) -> str:
    return escape_md(text)


def _build_bot_commands(bot_command_cls: Any) -> list[Any]:
    return [bot_command_cls(command=command, description=description) for command, description in _COMMAND_SPECS]


def _select_mp_link_targets(secrets: list[Any], label: str | None) -> list[Any]:
    """Return enabled secrets for /mp_link (all enabled or a specific label)."""
    if label:
        return [secret for secret in secrets if secret.enabled and secret.label == label]
    return [secret for secret in secrets if secret.enabled]


async def _start_polling(dispatcher: Any, bot: Any) -> None:
    # Polling runs in a worker thread; aiogram signal handlers are main-thread only.
    await dispatcher.start_polling(bot, handle_signals=False)


def _get_stats_text() -> str:
    from mtproxymaxpy import metrics as _metrics, process_manager

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
            lines.append(f"  {flag} `{_md(s.label)}`")
    return "\n".join(lines)


def _get_health_text() -> str:
    from mtproxymaxpy import doctor

    results = doctor.run_full_doctor()
    lines = ["🏥 *Health Check*", ""]
    for r in results:
        ok = r.get("ok")
        icon = "✅" if ok is True else ("❌" if ok is False else "⚠️")
        name = _md(r["name"])
        extra = _md(str(r.get("error", ""))) if r.get("error") else ""
        lines.append(f"{icon} {name}{(' — ' + extra) if extra else ''}")
    return "\n".join(lines)


def _run_polling(token: str, chat_id: str, interval_hours: int) -> None:
    global _loop, _bot, _dispatcher

    async def _main() -> None:
        nonlocal token, chat_id, interval_hours
        from aiogram import Bot, Dispatcher, Router
        from aiogram.filters import Command
        from aiogram.types import BotCommand, Message

        bot = Bot(token=token)
        dp = Dispatcher()
        router = Router(name="mtproxymaxpy-aiogram")

        _loop_ref = asyncio.get_running_loop()
        _set_runtime_state(_loop_ref, bot, dp)

        async def _authorised(msg: Message) -> bool:
            return bool(msg.chat and str(msg.chat.id) == chat_id)

        async def _send_text(text: str) -> None:
            await bot.send_message(chat_id, text, parse_mode="MarkdownV2")

        async def _send_chunked(lines: list[str], limit: int = 3500) -> None:
            chunk: list[str] = []
            chunk_len = 0
            for line in lines:
                line_len = len(line) + 1
                if chunk and chunk_len + line_len > limit:
                    await _send_text("\n".join(chunk))
                    chunk = [line]
                    chunk_len = line_len
                else:
                    chunk.append(line)
                    chunk_len += line_len
            if chunk:
                await _send_text("\n".join(chunk))

        async def _report_loop() -> None:
            while True:
                await asyncio.sleep(interval_hours * 3600)
                try:
                    await _send_text(_get_stats_text())
                except Exception as exc:
                    logger.warning("aiogram report loop send failed: %s", exc)

        @router.message(Command("status"))
        async def handle_status(msg: Message) -> None:
            if not await _authorised(msg):
                return
            await msg.answer(_get_stats_text(), parse_mode="MarkdownV2")

        @router.message(Command("users"))
        async def handle_users(msg: Message) -> None:
            if not await _authorised(msg):
                return
            await msg.answer(build_users_text(load_secrets(), md=_md), parse_mode="MarkdownV2")

        @router.message(Command("restart"))
        async def handle_restart(msg: Message) -> None:
            if not await _authorised(msg):
                return
            from mtproxymaxpy import process_manager

            await msg.answer("🔄 Restarting telemt…", parse_mode="MarkdownV2")
            try:
                pid = process_manager.restart()
                await msg.answer(f"✅ Restarted \\(PID `{pid}`\\)", parse_mode="MarkdownV2")
            except Exception as exc:
                await msg.answer(f"❌ Restart failed: `{_md(str(exc))}`", parse_mode="MarkdownV2")

        @router.message(Command("help"))
        @router.message(Command("start"))
        @router.message(Command("mp_help"))
        async def handle_help(msg: Message) -> None:
            if not await _authorised(msg):
                return
            await msg.answer(build_help_text(), parse_mode="MarkdownV2")

        @router.message(Command("mp_health"))
        async def handle_mp_health(msg: Message) -> None:
            if not await _authorised(msg):
                return
            await msg.answer(_get_health_text(), parse_mode="MarkdownV2")

        @router.message(Command("mp_traffic"))
        async def handle_mp_traffic(msg: Message) -> None:
            if not await _authorised(msg):
                return
            from mtproxymaxpy import metrics as _metrics

            mst = _metrics.get_stats()
            if not mst.get("available"):
                await msg.answer("❌ Metrics unavailable\\.", parse_mode="MarkdownV2")
                return
            text = build_mp_traffic_text(mst, md=_md, bytes_formatter=format_bytes)
            await msg.answer(text, parse_mode="MarkdownV2")

        @router.message(Command("mp_secrets"))
        async def handle_mp_secrets(msg: Message) -> None:
            if not await _authorised(msg):
                return
            from mtproxymaxpy import metrics as _metrics

            secrets = load_secrets()
            mst = _metrics.get_stats(timeout=2.0, max_age=5.0)
            lines = build_mp_secrets_lines(secrets, mst, md=_md, bytes_formatter=format_bytes)
            await _send_chunked(lines)

        @router.message(Command("mp_limits"))
        async def handle_mp_limits(msg: Message) -> None:
            if not await _authorised(msg):
                return
            parts = (msg.text or "").split(maxsplit=1)
            if len(parts) < 2:
                await msg.answer("Usage: /mp\\_limits \\<label\\>", parse_mode="MarkdownV2")
                return
            label = parts[1].strip()
            secret = next((s for s in load_secrets() if s.label == label), None)
            if secret is None:
                await msg.answer(f"❌ Not found: `{_md(label)}`", parse_mode="MarkdownV2")
                return
            await msg.answer(
                build_mp_limits_text(secret, md=_md, bytes_formatter=format_bytes), parse_mode="MarkdownV2"
            )

        @router.message(Command("mp_setlimit"))
        async def handle_mp_setlimit(msg: Message) -> None:
            if not await _authorised(msg):
                return
            from mtproxymaxpy.config.secrets import set_secret_limits
            from mtproxymaxpy.utils.validation import parse_human_bytes

            parts = (msg.text or "").split(maxsplit=3)
            if len(parts) < 4:
                await msg.answer(
                    "Usage: /mp\\_setlimit \\<label\\> \\<conns\\|ips\\|quota\\|expires\\> \\<value\\>",
                    parse_mode="MarkdownV2",
                )
                return

            _, label, field, value = parts
            try:
                kwargs: dict[str, Any] = {}
                if field == "conns":
                    kwargs["max_conns"] = int(value)
                elif field == "ips":
                    kwargs["max_ips"] = int(value)
                elif field == "quota":
                    kwargs["quota_bytes"] = parse_human_bytes(value)
                elif field == "expires":
                    kwargs["expires"] = value
                else:
                    await msg.answer(f"❌ Unknown field `{_md(field)}`", parse_mode="MarkdownV2")
                    return
                set_secret_limits(label, **kwargs)
                await msg.answer(f"✅ Updated `{_md(field)}` for `{_md(label)}`", parse_mode="MarkdownV2")
            except Exception as exc:
                await msg.answer(f"❌ {_md(str(exc))}", parse_mode="MarkdownV2")

        @router.message(Command("mp_upstreams"))
        async def handle_mp_upstreams(msg: Message) -> None:
            if not await _authorised(msg):
                return
            from mtproxymaxpy.config.upstreams import load_upstreams

            await msg.answer(build_mp_upstreams_text(load_upstreams(), md=_md), parse_mode="MarkdownV2")

        @router.message(Command("mp_link"))
        async def handle_mp_link(msg: Message) -> None:
            if not await _authorised(msg):
                return
            from mtproxymaxpy.utils.network import get_public_ip
            from mtproxymaxpy.utils.proxy_link import build_proxy_links, qr_api_url

            args = (msg.text or "").split(maxsplit=1)
            label = args[1].strip() if len(args) > 1 else None
            secrets = load_secrets()
            targets = _select_mp_link_targets(secrets, label)
            if not targets:
                await msg.answer("❌ Secret not found\\.", parse_mode="MarkdownV2")
                return

            settings = load_settings()
            srv = settings.custom_ip or get_public_ip() or "?"
            for secret in targets:
                tg, web = build_proxy_links(secret.key, settings.proxy_domain, srv, settings.proxy_port)
                qr_url = qr_api_url(web)
                await msg.answer(build_mp_link_text(secret.label, tg, web, qr_url, md=_md), parse_mode="MarkdownV2")

        @router.message(Command("mp_add"))
        async def handle_mp_add(msg: Message) -> None:
            if not await _authorised(msg):
                return
            from mtproxymaxpy.config.secrets import add_secret

            args = (msg.text or "").split(maxsplit=1)
            if len(args) < 2:
                await msg.answer("Usage: /mp\\_add \\<label\\>", parse_mode="MarkdownV2")
                return
            label = args[1].strip()
            try:
                secret = add_secret(label)
                await msg.answer(f"✅ Added `{_md(secret.label)}`: `{_md(secret.key)}`", parse_mode="MarkdownV2")
            except Exception as exc:
                await msg.answer(f"❌ {_md(str(exc))}", parse_mode="MarkdownV2")

        @router.message(Command("mp_remove"))
        async def handle_mp_remove(msg: Message) -> None:
            if not await _authorised(msg):
                return
            from mtproxymaxpy.config.secrets import remove_secret

            args = (msg.text or "").split(maxsplit=1)
            if len(args) < 2:
                await msg.answer("Usage: /mp\\_remove \\<label\\>", parse_mode="MarkdownV2")
                return
            label = args[1].strip()
            if remove_secret(label):
                await msg.answer(f"✅ Removed `{_md(label)}`", parse_mode="MarkdownV2")
            else:
                await msg.answer(f"❌ Not found: `{_md(label)}`", parse_mode="MarkdownV2")

        @router.message(Command("mp_rotate"))
        async def handle_mp_rotate(msg: Message) -> None:
            if not await _authorised(msg):
                return
            from mtproxymaxpy.config.secrets import rotate_secret

            args = (msg.text or "").split(maxsplit=1)
            if len(args) < 2:
                await msg.answer("Usage: /mp\\_rotate \\<label\\>", parse_mode="MarkdownV2")
                return
            label = args[1].strip()
            try:
                secret = rotate_secret(label)
                await msg.answer(
                    f"✅ Rotated `{_md(secret.label)}`\\. New key: `{_md(secret.key)}`",
                    parse_mode="MarkdownV2",
                )
            except KeyError as exc:
                await msg.answer(f"❌ {_md(str(exc))}", parse_mode="MarkdownV2")

        @router.message(Command("mp_enable"))
        async def handle_mp_enable(msg: Message) -> None:
            if not await _authorised(msg):
                return
            from mtproxymaxpy.config.secrets import enable_secret

            args = (msg.text or "").split(maxsplit=1)
            if len(args) < 2:
                await msg.answer("Usage: /mp\\_enable \\<label\\>", parse_mode="MarkdownV2")
                return
            label = args[1].strip()
            try:
                enable_secret(label)
                await msg.answer(f"✅ Enabled `{_md(label)}`", parse_mode="MarkdownV2")
            except Exception as exc:
                await msg.answer(f"❌ {_md(str(exc))}", parse_mode="MarkdownV2")

        @router.message(Command("mp_disable"))
        async def handle_mp_disable(msg: Message) -> None:
            if not await _authorised(msg):
                return
            from mtproxymaxpy.config.secrets import disable_secret

            args = (msg.text or "").split(maxsplit=1)
            if len(args) < 2:
                await msg.answer("Usage: /mp\\_disable \\<label\\>", parse_mode="MarkdownV2")
                return
            label = args[1].strip()
            try:
                disable_secret(label)
                await msg.answer(f"✅ Disabled `{_md(label)}`", parse_mode="MarkdownV2")
            except Exception as exc:
                await msg.answer(f"❌ {_md(str(exc))}", parse_mode="MarkdownV2")

        @router.message(Command("mp_update"))
        async def handle_mp_update(msg: Message) -> None:
            if not await _authorised(msg):
                return
            from mtproxymaxpy import process_manager
            from mtproxymaxpy.constants import TELEMT_VERSION

            await msg.answer("🔍 Checking for updates…", parse_mode="MarkdownV2")
            try:
                latest = process_manager.get_latest_version()
                if latest == TELEMT_VERSION:
                    await msg.answer(f"✅ Already on latest: `{_md(TELEMT_VERSION)}`", parse_mode="MarkdownV2")
                    return
                await msg.answer(
                    f"⬇️ Updating `{_md(TELEMT_VERSION)}` → `{_md(latest)}`…",
                    parse_mode="MarkdownV2",
                )
                was_running = process_manager.is_running()
                if was_running:
                    process_manager.stop()
                process_manager.download_binary(version=latest, force=True)
                if was_running:
                    from mtproxymaxpy.utils.network import get_public_ip

                    pid = process_manager.start(public_ip=get_public_ip() or "")
                    await msg.answer(f"✅ Updated and restarted \\(PID `{pid}`\\)", parse_mode="MarkdownV2")
                else:
                    await msg.answer("✅ Binary updated\\.", parse_mode="MarkdownV2")
            except Exception as exc:
                await msg.answer(f"❌ Update failed: `{_md(str(exc))}`", parse_mode="MarkdownV2")

        dp.include_router(router)
        try:
            await bot.set_my_commands(_build_bot_commands(BotCommand))
        except Exception as exc:
            logger.warning("aiogram set_my_commands failed: %s", exc)

        _started_event.set()
        report_task = asyncio.create_task(_report_loop(), name="tg-aiogram-report")
        try:
            await _start_polling(dp, bot)
        finally:
            report_task.cancel()
            try:
                await report_task
            except asyncio.CancelledError:
                pass
            await bot.session.close()

    try:
        asyncio.run(_main())
    except Exception as exc:
        logger.exception("aiogram polling thread crashed: %s", exc)
    finally:
        _reset_runtime_state()


def _set_runtime_state(loop: asyncio.AbstractEventLoop, bot: Any, dispatcher: Any) -> None:
    global _loop, _bot, _dispatcher
    _loop = loop
    _bot = bot
    _dispatcher = dispatcher


def _reset_runtime_state() -> None:
    global _loop, _bot, _dispatcher, _poll_thread
    _loop = None
    _bot = None
    _dispatcher = None
    _poll_thread = None
    _started_event.clear()


def start() -> None:
    """Start aiogram backend in a background polling thread."""
    global _poll_thread

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

    if _poll_thread is not None and _poll_thread.is_alive():
        logger.info("aiogram backend is already running")
        return

    try:
        import aiogram  # noqa: F401
    except Exception as exc:
        logger.warning("aiogram import failed: %s", exc)
        return

    _started_event.clear()
    _poll_thread = threading.Thread(
        target=_run_polling,
        args=(settings.telegram_bot_token, settings.telegram_chat_id, settings.telegram_interval),
        daemon=True,
        name="tg-aiogram-poll",
    )
    _poll_thread.start()
    logger.info("Telegram aiogram backend started")


def stop() -> None:
    """Stop Telegram backend and background tasks."""
    if _loop is not None and _dispatcher is not None:

        async def _shutdown() -> None:
            try:
                await _dispatcher.stop_polling()
            except Exception:
                pass
            try:
                if _bot is not None:
                    await _bot.session.close()
            except Exception:
                pass

        try:
            _loop.call_soon_threadsafe(lambda: asyncio.create_task(_shutdown()))
        except Exception:
            pass

    logger.info("Telegram aiogram backend stop requested")


def send_alert(text: str) -> None:
    """Send alert message through selected backend."""
    settings = load_settings()

    if not settings.telegram_enabled or _loop is None or _bot is None:
        return

    payload = escape_md(text)

    async def _send_async() -> None:
        await _bot.send_message(settings.telegram_chat_id, payload, parse_mode="MarkdownV2")

    try:
        _loop.call_soon_threadsafe(lambda: asyncio.create_task(_send_async()))
    except Exception:
        logger.warning("aiogram send_alert failed to schedule message")
