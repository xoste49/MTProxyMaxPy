"""Prometheus metrics fetching and parsing for telemt.

Telemt exposes a Prometheus-compatible /metrics endpoint.  This module
provides a thin wrapper that fetches, parses, and aggregates the raw samples
into a structured stats dict suitable for display in the TUI and CLI.
"""

from __future__ import annotations

import re
from typing import Any

import httpx


# ── Prometheus text-format parser ─────────────────────────────────────────────

_SAMPLE_RE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)"
    r"(?:\{(?P<labels>[^}]*)\})?\s+"
    r"(?P<value>[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|[+-]?Inf|NaN)"
    r"(?:\s+\d+)?$"
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
    """Parse Prometheus text format into a list of sample dicts.

    Each dict: ``{name: str, labels: dict[str, str], value: float}``
    """
    samples: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
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

def _total(samples: list[dict], name: str, **label_filter: str) -> float:
    total = 0.0
    for s in samples:
        if s["name"] != name:
            continue
        if all(s["labels"].get(k) == v for k, v in label_filter.items()):
            total += s["value"]
    return total


def _first(samples: list[dict], *names: str, **label_filter: str) -> float:
    for n in names:
        v = _total(samples, n, **label_filter)
        if v > 0:
            return v
    return 0.0


# ── Public API ─────────────────────────────────────────────────────────────────

def get_stats() -> dict[str, Any]:
    """Return a structured stats dict from the live Prometheus endpoint.

    Always returns a dict; ``available`` key indicates success.
    """
    try:
        raw = fetch_raw()
        samples = parse_metrics(raw)

        bytes_in = _first(
            samples,
            "telemt_bytes_in_total",
            "telemt_incoming_bytes_total",
            "telemt_rx_bytes_total",
        )
        bytes_out = _first(
            samples,
            "telemt_bytes_out_total",
            "telemt_outgoing_bytes_total",
            "telemt_tx_bytes_total",
        )
        active = _first(
            samples,
            "telemt_connections_active",
            "telemt_active_connections",
            "telemt_connections_current",
        )
        total_conns = _first(
            samples,
            "telemt_connections_total",
            "telemt_total_connections",
        )

        # Per-user stats: aggregate all samples that carry a "user" label
        user_stats: dict[str, dict[str, float]] = {}
        for s in samples:
            user = s["labels"].get("user")
            if not user:
                continue
            if user not in user_stats:
                user_stats[user] = {"bytes_in": 0.0, "bytes_out": 0.0, "active": 0.0}
            n = s["name"].lower()
            if "in" in n or "rx" in n or "incoming" in n or "recv" in n:
                user_stats[user]["bytes_in"] += s["value"]
            elif "out" in n or "tx" in n or "outgoing" in n or "sent" in n:
                user_stats[user]["bytes_out"] += s["value"]
            elif "active" in n or "current" in n:
                user_stats[user]["active"] += s["value"]

        return {
            "available": True,
            "bytes_in": int(bytes_in),
            "bytes_out": int(bytes_out),
            "active_connections": int(active),
            "total_connections": int(total_conns),
            "user_stats": user_stats,
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def get_user_stats(key: str) -> dict[str, float]:
    """Return stats for a specific user key (hex secret key)."""
    stats = get_stats()
    if not stats.get("available"):
        return {}
    return stats.get("user_stats", {}).get(key, {})
