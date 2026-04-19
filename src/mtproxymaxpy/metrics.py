"""
Prometheus metrics fetching and parsing for telemt.

Telemt exposes a Prometheus-compatible /metrics endpoint.  This module
provides a thin wrapper that fetches, parses, and aggregates the raw samples
into a structured stats dict suitable for display in the TUI and CLI.
"""

from __future__ import annotations

import re
import time
from typing import Any, cast

import httpx

_stats_cache: tuple[dict[str, Any], float] | None = None


# ── Prometheus text-format parser ─────────────────────────────────────────────

_SAMPLE_RE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)"
    r"(?:\{(?P<labels>[^}]*)\})?\s+"
    r"(?P<value>[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|[+-]?Inf|NaN)"
    r"(?:\s+\d+)?$",
)


def fetch_raw(timeout: float = 5.0) -> str:
    """Fetch the raw Prometheus metrics text from the local telemt endpoint."""
    from mtproxymaxpy.config.settings import load_settings

    settings = load_settings()
    url = f"http://localhost:{settings.proxy_metrics_port}/metrics"
    resp = httpx.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def parse_metrics(raw: str) -> list[dict[str, Any]]:
    """
    Parse Prometheus text format into a list of sample dicts.

    Each dict: ``{name: str, labels: dict[str, str], value: float}``
    """
    samples: list[dict[str, Any]] = []
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        m = _SAMPLE_RE.match(line)
        if not m:
            continue
        name = m.group("name")
        labels_str = m.group("labels") or ""
        raw_value = m.group("value")
        try:
            value = float(raw_value)
        except ValueError:
            continue
        labels: dict[str, str] = {}
        for part in re.finditer(r'(\w+)="([^"]*)"', labels_str):
            labels[part.group(1)] = part.group(2)
        samples.append({"name": name, "labels": labels, "value": value})
    return samples


# ── Aggregation helpers ────────────────────────────────────────────────────────


def _total(samples: list[dict[str, Any]], name: str, **label_filter: str) -> float:
    total = 0.0
    for s in samples:
        if s["name"] != name:
            continue
        if all(s["labels"].get(k) == v for k, v in label_filter.items()):
            total += s["value"]
    return total


def _first(samples: list[dict[str, Any]], *names: str, **label_filter: str) -> float:
    for n in names:
        v = _total(samples, n, **label_filter)
        if v > 0:
            return v
    return 0.0


def _sum_names(samples: list[dict[str, Any]], *names: str, **label_filter: str) -> float:
    total = 0.0
    for n in names:
        total += _total(samples, n, **label_filter)
    return total


# ── Public API ─────────────────────────────────────────────────────────────────


def _resolve_global_metrics(samples: list[dict[str, Any]]) -> tuple[float, float, float, float]:
    """Resolve the four global traffic counters from Prometheus samples."""
    bytes_in = _first(samples, "telemt_bytes_in_total", "telemt_incoming_bytes_total", "telemt_rx_bytes_total")
    if bytes_in <= 0:
        bytes_in = _sum_names(samples, "telemt_user_octets_from_client")

    bytes_out = _first(samples, "telemt_bytes_out_total", "telemt_outgoing_bytes_total", "telemt_tx_bytes_total")
    if bytes_out <= 0:
        bytes_out = _sum_names(samples, "telemt_user_octets_to_client")

    active = _first(samples, "telemt_connections_active", "telemt_active_connections", "telemt_connections_current")
    if active <= 0:
        active = _sum_names(samples, "telemt_user_connections_current")

    total_conns = _first(samples, "telemt_connections_total", "telemt_total_connections")
    if total_conns <= 0:
        total_conns = _sum_names(samples, "telemt_user_connections_total")

    return bytes_in, bytes_out, active, total_conns


def _aggregate_user_stats(samples: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Aggregate per-user traffic stats from Prometheus samples."""
    user_stats: dict[str, dict[str, float]] = {}
    for s in samples:
        user = s["labels"].get("user")
        if not user:
            continue
        if user not in user_stats:
            user_stats[user] = {"bytes_in": 0.0, "bytes_out": 0.0, "active": 0.0}
        n = s["name"].lower()
        if "incoming" in n or "rx" in n or "recv" in n or "bytes_in" in n or "octets_from_client" in n or "from_client" in n:
            user_stats[user]["bytes_in"] += s["value"]
        elif "outgoing" in n or "tx" in n or "sent" in n or "bytes_out" in n or "octets_to_client" in n or "to_client" in n:
            user_stats[user]["bytes_out"] += s["value"]
        elif "active" in n or "connections_current" in n:
            user_stats[user]["active"] += s["value"]
    return user_stats


def get_stats(*, timeout: float = 5.0, max_age: float = 0.0) -> dict[str, Any]:
    """
    Return a structured stats dict from the live Prometheus endpoint.

    Always returns a dict; ``available`` key indicates success.
    """
    global _stats_cache  # noqa: PLW0603

    if max_age > 0 and _stats_cache is not None:
        cached, ts = _stats_cache
        if time.monotonic() - ts <= max_age:
            return cached

    try:
        raw = fetch_raw(timeout=timeout)
        samples = parse_metrics(raw)

        bytes_in, bytes_out, active, total_conns = _resolve_global_metrics(samples)
        user_stats = _aggregate_user_stats(samples)

        result = {
            "available": True,
            "bytes_in": int(bytes_in),
            "bytes_out": int(bytes_out),
            "active_connections": int(active),
            "total_connections": int(total_conns),
            "user_stats": user_stats,
        }
        if max_age > 0:
            _stats_cache = (result, time.monotonic())
        return result
    except (ValueError, KeyError, OSError, RuntimeError, httpx.HTTPError) as exc:
        return {"available": False, "error": str(exc)}


def get_user_stats(label: str) -> dict[str, float]:
    """Return stats for a specific user label."""
    stats = get_stats()
    if not stats.get("available"):
        return {}
    return cast("dict[str, float]", stats.get("user_stats", {}).get(label, {}))
