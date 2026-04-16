"""Telegram message builders shared across bot backends."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any
from urllib.parse import parse_qs, urlparse

from aiogram.utils.formatting import Bold, Code, Text, TextLink


def _lines_to_text(lines: list[Any]) -> Text:
    parts: list[Any] = []
    for idx, line in enumerate(lines):
        if idx:
            parts.append("\n")
        parts.append(line)
    return Text(*parts)


def build_help_text() -> Text:
    """Build entity-based help text for bot commands."""
    lines: list[Any] = [
        Text("📋 ", Bold("MTProxyMaxPy Bot Commands")),
        "",
        "/status (/mp_status) - Proxy status",
        "/users - List users",
        "/restart (/mp_restart) - Restart proxy",
        "",
        "/mp_secrets - List secrets",
        "/mp_link [label] - Get proxy links + QR",
        "/mp_add <label> - Add secret",
        "/mp_remove <label> - Remove secret",
        "/mp_rotate <label> - Rotate secret",
        "/mp_enable <label> - Enable secret",
        "/mp_disable <label> - Disable secret",
        "/mp_limits <label> - Show user limits",
        "/mp_setlimit <label> <field> <val> - Set user limits",
        "/mp_upstreams - List upstreams",
        "/mp_traffic - Traffic report",
        "/mp_health - Health check",
        "",
        "/mp_update - Check for updates",
        "/mp_help - This help",
    ]
    return _lines_to_text(lines)


def build_users_text(secrets: Iterable[Any], *, md: Callable[[str], str] | None = None) -> Text:
    """Build entity-based text for /users response."""
    secrets_list = list(secrets)
    if not secrets_list:
        return Text("No users configured.")

    lines: list[Any] = [Bold("Users:")]
    for secret in secrets_list:
        flag = "✅" if secret.enabled else "❌"
        lines.append(Text("  ", flag, " ", Code(secret.label), " - ", Code(f"{secret.key[:8]}...")))
    return _lines_to_text(lines)


def build_mp_secrets_lines(
    secrets: Iterable[Any],
    metrics_stats: dict[str, Any],
    *,
    md: Callable[[str], str] | None = None,
    bytes_formatter: Callable[[float | int], str],
) -> list[Text]:
    """Build entity-based lines for /mp_secrets response."""
    user_stats = metrics_stats.get("user_stats", {}) if metrics_stats.get("available") else {}
    lines: list[Text] = [Text("📋 ", Bold("Secrets")), Text("")]

    if not metrics_stats.get("available"):
        err = str(metrics_stats.get("error", "metrics unavailable"))
        lines.append(Text("[metrics unavailable: ", Code(err), "]"))
        lines.append(Text(""))

    for secret in secrets:
        flag = "🟢" if secret.enabled else "🔴"
        stats = user_stats.get(secret.label, {})
        bytes_in = bytes_formatter(stats.get("bytes_in", 0)) if stats else "—"
        bytes_out = bytes_formatter(stats.get("bytes_out", 0)) if stats else "—"
        conns = str(int(stats.get("active", 0))) if stats else "0"
        lines.append(Text(flag, " ", Bold(secret.label), " - ", conns, " conn | ↓", bytes_in, " ↑", bytes_out))

    return lines


def build_mp_traffic_text(
    metrics_stats: dict[str, Any],
    *,
    md: Callable[[str], str] | None = None,
    bytes_formatter: Callable[[float | int], str],
) -> Text:
    """Build entity-based text for /mp_traffic response."""
    lines: list[Any] = [
        Text("📊 ", Bold("Traffic Report")),
        "",
        f"Total: ↓ {bytes_formatter(metrics_stats['bytes_in'])} ↑ {bytes_formatter(metrics_stats['bytes_out'])}",
        f"Active connections: {metrics_stats['active_connections']}",
        f"Lifetime connections: {metrics_stats['total_connections']}",
    ]
    return _lines_to_text(lines)


def build_mp_limits_text(
    secret: Any,
    *,
    md: Callable[[str], str] | None = None,
    bytes_formatter: Callable[[float | int], str],
) -> Text:
    """Build entity-based text for /mp_limits response."""
    conns_fmt = str(secret.max_conns) if secret.max_conns else "∞"
    ips_fmt = str(secret.max_ips) if secret.max_ips else "∞"
    quota_fmt = bytes_formatter(secret.quota_bytes) if secret.quota_bytes else "∞"
    exp_fmt = secret.expires or "never"
    lines: list[Any] = [
        Text("📋 ", Bold("User Limits")),
        "",
        Text("👤 ", Bold(secret.label)),
        f"  Conns: {conns_fmt} | IPs: {ips_fmt} | Quota: {quota_fmt} | Exp: {exp_fmt}",
    ]
    return _lines_to_text(lines)


def build_mp_upstreams_text(upstreams: Iterable[Any], *, md: Callable[[str], str] | None = None) -> Text:
    """Build entity-based text for /mp_upstreams response."""
    ups = list(upstreams)
    if not ups:
        return _lines_to_text([Text("📋 ", Bold("Upstreams")), "", "🟢 direct (weight: 10)"])

    lines: list[Any] = [Text("📋 ", Bold("Upstreams")), ""]
    for upstream in ups:
        flag = "🟢" if upstream.enabled else "🔴"
        addr = getattr(upstream, "addr", "")
        addr_info = f" — {addr}" if addr else ""
        lines.append(Text(flag, " ", Bold(upstream.name), f" ({upstream.type}{addr_info}) w:{upstream.weight}"))
    return _lines_to_text(lines)


def build_mp_link_text(
    label: str,
    tg_link: str,
    web_link: str,
    qr_url: str,
    *,
    md: Callable[[str], str] | None = None,
) -> Text:
    """Build entity-based text for /mp_link response."""
    parsed = urlparse(web_link)
    query = parse_qs(parsed.query)
    server = query.get("server", [""])[0]
    port = query.get("port", [""])[0]
    secret = query.get("secret", [""])[0]

    lines: list[Any] = [
        Text("🔗 ", Bold("Proxy Details")),
        "",
        Text("🏷 ", Bold(label)),
        Text("🔗 ", TextLink("Connect", url=web_link)),
    ]
    if server and port and secret:
        lines.append(Text("📡 ", Code(f"{server}:{port}"), " | 🔑 ", Code(secret)))
    lines += [
        "",
        TextLink("tg link", url=tg_link),
        "",
        TextLink("QR code", url=qr_url),
    ]
    return _lines_to_text(lines)
