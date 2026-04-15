"""Telegram message builders shared across bot backends."""

from __future__ import annotations

from typing import Any, Callable, Iterable
from urllib.parse import parse_qs, urlparse


def build_help_text() -> str:
    """Build MarkdownV2-safe help text for bot commands."""
    lines = [
        "📋 *MTProxyMaxPy Bot Commands*",
        "",
        "/status \\(/mp\\_status\\) — Proxy status",
        "/users — List users",
        "/restart \\(/mp\\_restart\\) — Restart proxy",
        "",
        "/mp\\_secrets — List secrets",
        "/mp\\_link \\[label\\] — Get proxy links \\+ QR",
        "/mp\\_add \\<label\\> — Add secret",
        "/mp\\_remove \\<label\\> — Remove secret",
        "/mp\\_rotate \\<label\\> — Rotate secret",
        "/mp\\_enable \\<label\\> — Enable secret",
        "/mp\\_disable \\<label\\> — Disable secret",
        "/mp\\_limits \\<label\\> — Show user limits",
        "/mp\\_setlimit \\<label\\> \\<field\\> \\<val\\> — Set user limits",
        "/mp\\_upstreams — List upstreams",
        "/mp\\_traffic — Traffic report",
        "/mp\\_health — Health check",
        "",
        "/mp\\_update — Check for updates",
        "/mp\\_help — This help",
    ]
    return "\n".join(lines)


def build_users_text(secrets: Iterable[Any], *, md: Callable[[str], str]) -> str:
    """Build MarkdownV2-safe text for /users response."""
    secrets_list = list(secrets)
    if not secrets_list:
        return "No users configured\\."

    lines = ["*Users:*"]
    for secret in secrets_list:
        flag = "✅" if secret.enabled else "❌"
        lines.append(f"  {flag} `{md(secret.label)}` — `{secret.key[:8]}…`")
    return "\n".join(lines)


def build_mp_secrets_lines(
    secrets: Iterable[Any],
    metrics_stats: dict[str, Any],
    *,
    md: Callable[[str], str],
    bytes_formatter: Callable[[float | int], str],
) -> list[str]:
    """Build MarkdownV2-safe lines for /mp_secrets response."""
    user_stats = metrics_stats.get("user_stats", {}) if metrics_stats.get("available") else {}
    lines = ["📋 *Secrets*", ""]

    if not metrics_stats.get("available"):
        err = md(str(metrics_stats.get("error", "metrics unavailable")))
        lines.append(f"[metrics unavailable: `{err}`]")
        lines.append("")

    for secret in secrets:
        flag = "🟢" if secret.enabled else "🔴"
        stats = user_stats.get(secret.label, {})
        bytes_in = bytes_formatter(stats.get("bytes_in", 0)) if stats else "—"
        bytes_out = bytes_formatter(stats.get("bytes_out", 0)) if stats else "—"
        conns = str(int(stats.get("active", 0))) if stats else "0"
        lines.append(f"{flag} *{md(secret.label)}* — {md(conns)} conn | ↓{md(bytes_in)} ↑{md(bytes_out)}")

    return lines


def build_mp_traffic_text(
    metrics_stats: dict[str, Any],
    *,
    md: Callable[[str], str],
    bytes_formatter: Callable[[float | int], str],
) -> str:
    """Build MarkdownV2-safe text for /mp_traffic response."""
    lines = [
        "📊 *Traffic Report*",
        "",
        f"Total: ↓ {md(bytes_formatter(metrics_stats['bytes_in']))} ↑ {md(bytes_formatter(metrics_stats['bytes_out']))}",
        f"Active connections: {md(str(metrics_stats['active_connections']))}",
        f"Lifetime connections: {md(str(metrics_stats['total_connections']))}",
    ]
    return "\n".join(lines)


def build_mp_limits_text(
    secret: Any,
    *,
    md: Callable[[str], str],
    bytes_formatter: Callable[[float | int], str],
) -> str:
    """Build MarkdownV2-safe text for /mp_limits response."""
    conns_fmt = str(secret.max_conns) if secret.max_conns else "∞"
    ips_fmt = str(secret.max_ips) if secret.max_ips else "∞"
    quota_fmt = md(bytes_formatter(secret.quota_bytes)) if secret.quota_bytes else "∞"
    exp_fmt = secret.expires or "never"
    lines = [
        "📋 *User Limits*",
        "",
        f"👤 *{md(secret.label)}*",
        f"  Conns: {md(conns_fmt)} | IPs: {md(ips_fmt)} | Quota: {quota_fmt} | Exp: {md(exp_fmt)}",
    ]
    return "\n".join(lines)


def build_mp_upstreams_text(upstreams: Iterable[Any], *, md: Callable[[str], str]) -> str:
    """Build MarkdownV2-safe text for /mp_upstreams response."""
    ups = list(upstreams)
    if not ups:
        return "📋 *Upstreams*\n\n🟢 direct \\(weight: 10\\)"

    lines = ["📋 *Upstreams*", ""]
    for upstream in ups:
        flag = "🟢" if upstream.enabled else "🔴"
        addr = getattr(upstream, "addr", "")
        addr_info = f" — {addr}" if addr else ""
        lines.append(
            f"{flag} *{md(upstream.name)}* \\({md(upstream.type)}{md(addr_info)}\\) w:{md(str(upstream.weight))}"
        )
    return "\n".join(lines)


def build_mp_link_text(label: str, tg_link: str, web_link: str, qr_url: str, *, md: Callable[[str], str]) -> str:
    """Build MarkdownV2-safe text for /mp_link response."""
    parsed = urlparse(web_link)
    query = parse_qs(parsed.query)
    server = query.get("server", [""])[0]
    port = query.get("port", [""])[0]
    secret = query.get("secret", [""])[0]

    lines = [
        "🔗 *Proxy Details*",
        "",
        f"🏷 *{md(label)}*",
        f"🔗 [Connect]({md(web_link)})",
    ]
    if server and port and secret:
        lines.append(f"📡 `{md(f'{server}:{port}')}` | 🔑 `{md(secret)}`")
    lines += [
        "",
        f"[tg link]({md(tg_link)})",
        "",
        f"[QR code]({md(qr_url)})",
    ]
    return "\n".join(lines)
