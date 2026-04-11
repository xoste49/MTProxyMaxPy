"""Upstream (SOCKS5/4) routing entries — Pydantic model + JSON persistence."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from mtproxymaxpy.constants import UPSTREAMS_FILE


class Upstream(BaseModel):
    name: str
    type: Literal["direct", "socks5", "socks4"] = "direct"
    addr: str = ""          # "host:port" for SOCKS
    user: str = ""
    password: str = ""
    weight: int = Field(100, ge=1, le=100)
    iface: str = ""         # source network interface (optional)
    enabled: bool = True


def load_upstreams(path: Path = UPSTREAMS_FILE) -> list[Upstream]:
    if not path.exists():
        return []
    with open(path) as fh:
        data = json.load(fh)
    return [Upstream.model_validate(item) for item in data]


def save_upstreams(items: list[Upstream], path: Path = UPSTREAMS_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [item.model_dump() for item in items]
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── Mutation helpers ───────────────────────────────────────────────────────────

def _set_upstream_field(name: str, field: str, value, path: Path = UPSTREAMS_FILE) -> Upstream:
    items = load_upstreams(path)
    for i, u in enumerate(items):
        if u.name == name:
            items[i] = u.model_copy(update={field: value})
            save_upstreams(items, path)
            return items[i]
    raise KeyError(f"Upstream {name!r} not found")


def enable_upstream(name: str, path: Path = UPSTREAMS_FILE) -> Upstream:
    return _set_upstream_field(name, "enabled", True, path)


def disable_upstream(name: str, path: Path = UPSTREAMS_FILE) -> Upstream:
    return _set_upstream_field(name, "enabled", False, path)


def test_upstream(name: str, timeout: float = 10.0) -> dict:
    """Test connectivity through an upstream proxy.

    Returns ``{ok: bool, error: str|None, latency_ms: float|None}``.
    """
    import shutil
    import time

    items = load_upstreams()
    upstream = next((u for u in items if u.name == name), None)
    if upstream is None:
        raise KeyError(f"Upstream {name!r} not found")
    if upstream.type == "direct":
        return {"ok": True, "error": None, "latency_ms": None, "note": "direct — no test needed"}
    if not shutil.which("curl"):
        return {"ok": None, "error": "curl not available", "latency_ms": None}

    cmd = [
        "curl", "-s", "--max-time", str(int(timeout)),
        "--proxy", f"{upstream.type}://"
        + (f"{upstream.user}:{upstream.password}@" if upstream.user else "")
        + upstream.addr,
        "-o", "/dev/null", "-w", "%{http_code}",
        "https://api.ipify.org",
    ]
    t0 = time.monotonic()
    try:
        import subprocess
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 2)
        latency_ms = (time.monotonic() - t0) * 1000
        ok = result.returncode == 0
        return {"ok": ok, "error": result.stderr.strip() or None, "latency_ms": round(latency_ms, 1)}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "latency_ms": None}
