"""Telegram message builders shared across bot backends."""

from __future__ import annotations

from typing import Any, Callable, Iterable


def build_help_text() -> str:
    """Build MarkdownV2-safe help text for bot commands."""
    lines = [
        "📋 *MTProxyMaxPy Bot Commands*",
        "",
        "/status — proxy status",
        "/users — list users",
        "/restart — restart proxy",
        "",
        "/mp\\_health — full diagnostics",
        "/mp\\_secrets — secrets with traffic stats",
        "/mp\\_link \\[label\\] — proxy link \\+ QR",
        "/mp\\_traffic — traffic statistics",
        "/mp\\_upstreams — list upstreams",
        "",
        "/mp\\_add \\<label\\> — add secret",
        "/mp\\_remove \\<label\\> — remove secret",
        "/mp\\_rotate \\<label\\> — rotate key",
        "/mp\\_enable \\<label\\> — enable",
        "/mp\\_disable \\<label\\> — disable",
        "/mp\\_limits \\<label\\> — show limits",
        "/mp\\_setlimit \\<label\\> \\<field\\> \\<val\\>",
        "",
        "/mp\\_update — update telemt binary",
        "/mp\\_help — this message",
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
    lines = ["*Secrets:*", ""]

    if not metrics_stats.get("available"):
        err = md(str(metrics_stats.get("error", "metrics unavailable")))
        lines.append(f"[metrics unavailable: `{err}`]")
        lines.append("")

    for secret in secrets:
        flag = "✅" if secret.enabled else "❌"
        stats = user_stats.get(secret.label, {})
        bytes_in = bytes_formatter(stats.get("bytes_in", 0)) if stats else "—"
        bytes_out = bytes_formatter(stats.get("bytes_out", 0)) if stats else "—"
        conns = str(int(stats.get("active", 0))) if stats else "—"
        lines.append(f"{flag} `{md(secret.label)}`\n    ↑{md(bytes_out)} ↓{md(bytes_in)} {md(f'conns={conns}')}")

    return lines


def build_mp_traffic_text(
    metrics_stats: dict[str, Any],
    *,
    md: Callable[[str], str],
    bytes_formatter: Callable[[float | int], str],
) -> str:
    """Build MarkdownV2-safe text for /mp_traffic response."""
    lines = [
        "📊 *Traffic*",
        f"↑ Out: `{md(bytes_formatter(metrics_stats['bytes_out']))}`",
        f"↓ In:  `{md(bytes_formatter(metrics_stats['bytes_in']))}`",
        f"Active: `{metrics_stats['active_connections']}`",
        f"Total:  `{metrics_stats['total_connections']}`",
    ]
    return "\n".join(lines)


def build_mp_limits_text(
    secret: Any,
    *,
    md: Callable[[str], str],
    bytes_formatter: Callable[[float | int], str],
) -> str:
    """Build MarkdownV2-safe text for /mp_limits response."""
    lines = [
        f"🔒 *{md(secret.label)} limits*",
        f"max\\_conns: `{secret.max_conns or 'unlimited'}`",
        f"max\\_ips: `{secret.max_ips or 'unlimited'}`",
        f"quota: `{md(bytes_formatter(secret.quota_bytes)) if secret.quota_bytes else 'unlimited'}`",
        f"expires: `{secret.expires or 'never'}`",
    ]
    return "\n".join(lines)


def build_mp_upstreams_text(upstreams: Iterable[Any], *, md: Callable[[str], str]) -> str:
    """Build MarkdownV2-safe text for /mp_upstreams response."""
    ups = list(upstreams)
    if not ups:
        return "No upstreams configured\\."

    lines = ["🔀 *Upstreams:*"]
    for upstream in ups:
        flag = "✅" if upstream.enabled else "❌"
        lines.append(
            f"  {flag} `{md(upstream.name)}` {md(upstream.type)} `{md(upstream.addr)}` {md(f'w={upstream.weight}')}"
        )
    return "\n".join(lines)


def build_mp_link_text(label: str, tg_link: str, web_link: str, qr_url: str, *, md: Callable[[str], str]) -> str:
    """Build MarkdownV2-safe text for /mp_link response."""
    lines = [
        f"🔗 *{md(label)}*",
        "",
        f"`{md(tg_link)}`",
        "",
        f"`{md(web_link)}`",
        "",
        f"[QR code]({md(qr_url)})",
    ]
    return "\n".join(lines)
