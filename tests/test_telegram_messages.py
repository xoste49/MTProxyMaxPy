from __future__ import annotations

from types import SimpleNamespace

from mtproxymaxpy.telegram_messages import (
    build_help_text,
    build_mp_link_text,
    build_mp_limits_text,
    build_mp_secrets_lines,
    build_mp_traffic_text,
    build_mp_upstreams_text,
    build_users_text,
)
from mtproxymaxpy.utils.formatting import escape_md, format_bytes


def test_build_mp_secrets_lines_escapes_markdown() -> None:
    secrets = [SimpleNamespace(label="alice_user", key="a" * 32, enabled=True)]
    stats = {
        "available": True,
        "user_stats": {"alice_user": {"bytes_in": 1024, "bytes_out": 2048, "active": 3}},
    }

    lines = build_mp_secrets_lines(secrets, stats, md=escape_md, bytes_formatter=format_bytes)
    payload = "\n".join(lines)

    assert "alice\\_user" in payload
    assert "conn" in payload


def test_build_mp_secrets_lines_uses_label_keyed_user_stats() -> None:
    """Regression: metrics user_stats are keyed by user label, not secret key."""
    secrets = [SimpleNamespace(label="alice_user", key="a" * 32, enabled=True)]
    stats = {
        "available": True,
        "user_stats": {
            "alice_user": {
                "bytes_in": 1024,
                "bytes_out": 2048,
                "active": 3,
            }
        },
    }

    lines = build_mp_secrets_lines(secrets, stats, md=escape_md, bytes_formatter=format_bytes)
    payload = "\n".join(lines)

    assert "3 conn | ↓1\\.0 KB ↑2\\.0 KB" in payload


def test_build_mp_traffic_text_renders_expected_fields() -> None:
    stats = {
        "bytes_in": 1024,
        "bytes_out": 2048,
        "active_connections": 3,
        "total_connections": 10,
    }

    text = build_mp_traffic_text(stats, md=escape_md, bytes_formatter=format_bytes)

    assert "*Traffic Report*" in text
    assert "Active connections: 3" in text
    assert "Lifetime connections: 10" in text


def test_build_users_text_handles_empty_and_escapes_label() -> None:
    assert build_users_text([], md=escape_md) == "No users configured\\."

    secrets = [SimpleNamespace(label="alice_user", key="a" * 32, enabled=True)]
    text = build_users_text(secrets, md=escape_md)

    assert "*Users:*" in text
    assert "alice\\_user" in text


def test_build_mp_limits_text_formats_values() -> None:
    secret = SimpleNamespace(label="alice_user", max_conns=5, max_ips=2, quota_bytes=1024, expires="2030-01-01")
    text = build_mp_limits_text(secret, md=escape_md, bytes_formatter=format_bytes)

    assert "alice\\_user" in text
    assert "Conns: 5" in text
    assert "IPs: 2" in text
    assert "Exp: 2030\\-01\\-01" in text


def test_build_mp_upstreams_text_empty_and_fields() -> None:
    assert build_mp_upstreams_text([], md=escape_md) == "📋 *Upstreams*\n\n🟢 direct \\(weight: 10\\)"

    upstreams = [SimpleNamespace(name="up_1", type="socks5", addr="1.1.1.1:1080", weight=10, enabled=True)]
    text = build_mp_upstreams_text(upstreams, md=escape_md)

    assert "*Upstreams*" in text
    assert "up\\_1" in text
    assert "w:10" in text


def test_build_mp_link_text_contains_all_parts() -> None:
    text = build_mp_link_text(
        "alice_user",
        "tg://proxy",
        "https://t.me/proxy?server=1.2.3.4&port=443&secret=abc",
        "https://qr",
        md=escape_md,
    )

    assert "alice\\_user" in text
    assert "[Connect](https://t\\.me/proxy?server\\=1\\.2\\.3\\.4&port\\=443&secret\\=abc)" in text
    assert "[tg link](tg://proxy)" in text
    assert "[QR code](https://qr)" in text
    assert text.count("](") == 3


def test_build_help_text_contains_core_commands() -> None:
    text = build_help_text()

    assert "/status" in text
    assert "/mp\\_secrets" in text
    assert "/mp\\_update" in text
