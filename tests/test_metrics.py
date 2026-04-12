from __future__ import annotations

from types import SimpleNamespace

import pytest

from mtproxymaxpy import metrics


def test_parse_metrics_skips_comments_and_invalid_lines() -> None:
    raw = """
# HELP telemt_bytes_in_total Incoming bytes
telemt_bytes_in_total 123
telemt_bytes_out_total{user="alice"} 45
bad line
telemt_active_connections{user="alice",kind="x"} 2
"""
    parsed = metrics.parse_metrics(raw)
    assert len(parsed) == 3
    assert parsed[0]["name"] == "telemt_bytes_in_total"
    assert parsed[0]["value"] == 123.0
    assert parsed[1]["labels"]["user"] == "alice"


def test_total_and_first_helpers() -> None:
    samples = [
        {"name": "a", "labels": {}, "value": 1.0},
        {"name": "a", "labels": {"user": "u1"}, "value": 3.0},
        {"name": "b", "labels": {}, "value": 9.0},
    ]
    assert metrics._total(samples, "a") == 4.0
    assert metrics._total(samples, "a", user="u1") == 3.0
    assert metrics._first(samples, "x", "a") == 4.0
    assert metrics._first(samples, "x", "y") == 0.0


def test_get_stats_success_and_user_aggregation(monkeypatch: pytest.MonkeyPatch) -> None:
    metrics._stats_cache = None
    raw = "\n".join(
        [
            "telemt_incoming_bytes_total 100",
            "telemt_outgoing_bytes_total 200",
            "telemt_active_connections 3",
            "telemt_total_connections 4",
            'telemt_rx_bytes_total{user="alice"} 10',
            'telemt_tx_bytes_total{user="alice"} 20',
            'telemt_active_connections{user="alice"} 1',
        ]
    )
    monkeypatch.setattr(metrics, "fetch_raw", lambda timeout=5.0: raw)

    stats = metrics.get_stats()
    assert stats["available"] is True
    assert stats["bytes_in"] == 100
    assert stats["bytes_out"] == 200
    assert stats["active_connections"] == 4
    assert stats["total_connections"] == 4
    assert stats["user_stats"]["alice"]["bytes_in"] == 10.0
    assert stats["user_stats"]["alice"]["bytes_out"] == 20.0
    assert stats["user_stats"]["alice"]["active"] == 1.0


def test_get_stats_uses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    metrics._stats_cache = None
    calls = {"n": 0}

    def _fake_fetch(timeout=5.0):
        calls["n"] += 1
        return "telemt_bytes_in_total 1"

    t = {"v": 100.0}
    monkeypatch.setattr(metrics, "fetch_raw", _fake_fetch)
    monkeypatch.setattr(metrics.time, "monotonic", lambda: t["v"])

    first = metrics.get_stats(max_age=10)
    assert first["available"] is True
    t["v"] = 105.0
    second = metrics.get_stats(max_age=10)
    assert second == first
    assert calls["n"] == 1

    t["v"] = 200.0
    metrics.get_stats(max_age=10)
    assert calls["n"] == 2


def test_get_stats_error_path(monkeypatch: pytest.MonkeyPatch) -> None:
    metrics._stats_cache = None

    def _boom(timeout=5.0):
        raise RuntimeError("boom")

    monkeypatch.setattr(metrics, "fetch_raw", _boom)
    out = metrics.get_stats()
    assert out["available"] is False
    assert "boom" in out["error"]


def test_fetch_raw_builds_metrics_url(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    fake_settings = SimpleNamespace(proxy_metrics_port=7777)

    class _Resp:
        text = "ok"

        def raise_for_status(self):
            return None

    seen = {"url": "", "timeout": None}

    def _fake_get(url, timeout):
        seen["url"] = url
        seen["timeout"] = timeout
        return _Resp()

    mod = SimpleNamespace(load_settings=lambda: fake_settings)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.config.settings", mod)
    monkeypatch.setattr(metrics.httpx, "get", _fake_get)

    raw = metrics.fetch_raw(timeout=2.5)
    assert raw == "ok"
    assert seen["url"] == "http://localhost:7777/metrics"
    assert seen["timeout"] == 2.5


def test_get_user_stats(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metrics, "get_stats", lambda: {"available": False})
    assert metrics.get_user_stats("alice") == {}

    monkeypatch.setattr(
        metrics,
        "get_stats",
        lambda: {"available": True, "user_stats": {"alice": {"bytes_in": 1.0}}},
    )
    assert metrics.get_user_stats("alice") == {"bytes_in": 1.0}
