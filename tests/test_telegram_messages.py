from __future__ import annotations

from types import SimpleNamespace

from mtproxymaxpy.telegram_messages import (
    build_help_text,
    build_mp_limits_text,
    build_mp_link_text,
    build_mp_secrets_lines,
    build_mp_traffic_text,
    build_mp_upstreams_text,
    build_users_text,
)
from mtproxymaxpy.utils.formatting import format_bytes


def _render(content) -> tuple[str, list[object]]:
    kwargs = content.as_kwargs()
    return kwargs["text"], kwargs["entities"]


def test_build_mp_secrets_lines_entity_output() -> None:
    secrets = [SimpleNamespace(label="alice_user", key="a" * 32, enabled=True)]
    stats = {
        "available": True,
        "user_stats": {"alice_user": {"bytes_in": 1024, "bytes_out": 2048, "active": 3}},
    }

    lines = build_mp_secrets_lines(secrets, stats, bytes_formatter=format_bytes)
    payload = "\n".join(line.as_kwargs()["text"] for line in lines)

    assert "alice_user" in payload
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
            },
        },
    }

    lines = build_mp_secrets_lines(secrets, stats, bytes_formatter=format_bytes)
    payload = "\n".join(line.as_kwargs()["text"] for line in lines)

    assert "3 conn | ↓1.0 KB ↑2.0 KB" in payload


def test_build_mp_traffic_text_renders_expected_fields() -> None:
    stats = {
        "bytes_in": 1024,
        "bytes_out": 2048,
        "active_connections": 3,
        "total_connections": 10,
    }

    text, entities = _render(build_mp_traffic_text(stats, bytes_formatter=format_bytes))

    assert "Traffic Report" in text
    assert "Active connections: 3" in text
    assert "Lifetime connections: 10" in text
    assert entities


def test_build_users_text_handles_empty_and_label() -> None:
    text, _ = _render(build_users_text([]))
    assert text == "No users configured."

    secrets = [SimpleNamespace(label="alice_user", key="a" * 32, enabled=True)]
    text, entities = _render(build_users_text(secrets))

    assert "Users:" in text
    assert "alice_user" in text
    assert entities


def test_build_mp_limits_text_formats_values() -> None:
    secret = SimpleNamespace(label="alice_user", max_conns=5, max_ips=2, quota_bytes=1024, expires="2030-01-01")
    text, _ = _render(build_mp_limits_text(secret, bytes_formatter=format_bytes))

    assert "alice_user" in text
    assert "Conns: 5" in text
    assert "IPs: 2" in text
    assert "Exp: 2030-01-01" in text


def test_build_mp_upstreams_text_empty_and_fields() -> None:
    text, _ = _render(build_mp_upstreams_text([]))
    assert text == "📋 Upstreams\n\n🟢 direct (weight: 10)"

    upstreams = [SimpleNamespace(name="up_1", type="socks5", addr="1.1.1.1:1080", weight=10, enabled=True)]
    text, entities = _render(build_mp_upstreams_text(upstreams))

    assert "Upstreams" in text
    assert "up_1" in text
    assert "w:10" in text
    assert entities


def test_build_mp_link_text_contains_all_parts() -> None:
    text, entities = _render(
        build_mp_link_text(
            "alice_user",
            "tg://proxy",
            "https://t.me/proxy?server=1.2.3.4&port=443&secret=abc",
            "https://qr",
        ),
    )

    assert "alice_user" in text
    assert "Connect" in text
    assert "tg link" in text
    assert "QR code" in text
    assert len([e for e in entities if getattr(e, "type", None) == "text_link"]) == 3


def test_build_help_text_contains_core_commands() -> None:
    text, entities = _render(build_help_text())

    assert "/status" in text
    assert "/mp_secrets" in text
    assert "/mp_update" in text
    assert entities
