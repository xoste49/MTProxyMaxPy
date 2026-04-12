"""Upstream (SOCKS5/4) routing entries — Pydantic model + JSON persistence."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from mtproxymaxpy.constants import UPSTREAMS_FILE

DEFAULT_UPSTREAM_WEIGHT = 10
_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_ADDR_RE = re.compile(r"^[a-zA-Z0-9._-]+:[0-9]+$")


class Upstream(BaseModel):
    name: str
    type: Literal["direct", "socks5", "socks4"] = "direct"
    addr: str = ""  # "host:port" for SOCKS
    user: str = ""
    password: str = ""
    weight: int = Field(DEFAULT_UPSTREAM_WEIGHT, ge=1, le=100)
    iface: str = ""  # source network interface (optional)
    enabled: bool = True


def _default_direct_upstream() -> Upstream:
    return Upstream(name="direct", type="direct", weight=DEFAULT_UPSTREAM_WEIGHT, enabled=True)


def _assert_valid_name(name: str) -> None:
    if not _NAME_RE.fullmatch(name) or len(name) > 32:
        raise ValueError("Name must match [a-zA-Z0-9_-] and be <= 32 chars")


def _assert_safe_text(value: str, field: str) -> None:
    if any(ch in value for ch in ("|", '"', "\\")):
        raise ValueError(f"{field} cannot contain '|', '\"', or '\\'")


def _normalize_and_validate_addr(type_: str, addr: str) -> str:
    a = addr.strip()
    if type_ == "direct":
        return ""
    if not a:
        raise ValueError(f"Address (host:port) is required for {type_} upstreams")
    if not _ADDR_RE.fullmatch(a):
        raise ValueError("Address must be in host:port format")
    port = int(a.rsplit(":", 1)[1])
    if port < 1 or port > 65535:
        raise ValueError("Port must be 1-65535")
    return a


def load_upstreams(path: Path = UPSTREAMS_FILE) -> list[Upstream]:
    if not path.exists():
        return [_default_direct_upstream()]

    try:
        with open(path) as fh:
            data = json.load(fh)
    except Exception:
        return [_default_direct_upstream()]

    items: list[Upstream] = []
    for item in data:
        try:
            u = Upstream.model_validate(item)
        except Exception:
            continue
        if u.type != "direct" and not u.addr.strip():
            continue
        items.append(u)

    return items or [_default_direct_upstream()]


def save_upstreams(items: list[Upstream], path: Path = UPSTREAMS_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [item.model_dump() for item in (items or [_default_direct_upstream()])]
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


def add_upstream(
    name: str,
    *,
    type_: str = "socks5",
    addr: str = "",
    user: str = "",
    password: str = "",
    weight: int = DEFAULT_UPSTREAM_WEIGHT,
    iface: str = "",
    path: Path = UPSTREAMS_FILE,
) -> Upstream:
    items = load_upstreams(path)
    _assert_valid_name(name)
    if any(u.name == name for u in items):
        raise ValueError(f"Upstream {name!r} already exists")

    t = type_.strip().lower()
    if t not in ("direct", "socks5", "socks4"):
        raise ValueError("Type must be: direct, socks5, or socks4")

    normalized_addr = _normalize_and_validate_addr(t, addr)
    _assert_safe_text(user, "Username")
    _assert_safe_text(password, "Password")
    _assert_safe_text(iface, "Interface")

    if weight < 1 or weight > 100:
        raise ValueError("Weight must be 1-100")

    if t == "socks4":
        password = ""

    item = Upstream(
        name=name,
        type=t,  # type: ignore[arg-type]
        addr=normalized_addr,
        user=user,
        password=password,
        weight=weight,
        iface=iface,
        enabled=True,
    )
    items.append(item)
    save_upstreams(items, path)
    return item


def remove_upstream(name: str, path: Path = UPSTREAMS_FILE) -> Upstream:
    items = load_upstreams(path)
    if len(items) <= 1:
        raise ValueError("Cannot remove the last upstream")

    idx = next((i for i, u in enumerate(items) if u.name == name), -1)
    if idx < 0:
        raise KeyError(f"Upstream {name!r} not found")

    if items[idx].enabled:
        enabled_others = sum(1 for i, u in enumerate(items) if i != idx and u.enabled)
        if enabled_others == 0:
            raise ValueError("Cannot remove the last enabled upstream")

    removed = items.pop(idx)
    save_upstreams(items, path)
    return removed


def set_upstream_enabled(name: str, enabled: bool, path: Path = UPSTREAMS_FILE) -> Upstream:
    items = load_upstreams(path)
    idx = next((i for i, u in enumerate(items) if u.name == name), -1)
    if idx < 0:
        raise KeyError(f"Upstream {name!r} not found")

    if items[idx].enabled and not enabled:
        enabled_count = sum(1 for u in items if u.enabled)
        if enabled_count <= 1:
            raise ValueError("Cannot disable the last enabled upstream")

    items[idx] = items[idx].model_copy(update={"enabled": enabled})
    save_upstreams(items, path)
    return items[idx]


def enable_upstream(name: str, path: Path = UPSTREAMS_FILE) -> Upstream:
    return set_upstream_enabled(name, True, path)


def disable_upstream(name: str, path: Path = UPSTREAMS_FILE) -> Upstream:
    return set_upstream_enabled(name, False, path)


def toggle_upstream(name: str, path: Path = UPSTREAMS_FILE) -> Upstream:
    items = load_upstreams(path)
    current = next((u for u in items if u.name == name), None)
    if current is None:
        raise KeyError(f"Upstream {name!r} not found")
    return set_upstream_enabled(name, not current.enabled, path)


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
    if not shutil.which("curl"):
        return {"ok": None, "error": "curl not available", "latency_ms": None}

    cmd = ["curl", "-s", "--max-time", str(int(timeout))]
    if upstream.iface:
        cmd += ["--interface", upstream.iface]
    if upstream.type != "direct":
        cmd += [
            "--proxy",
            f"{upstream.type}://" + (f"{upstream.user}:{upstream.password}@" if upstream.user else "") + upstream.addr,
        ]
    cmd += ["-o", "/dev/null", "-w", "%{http_code}", "https://api.ipify.org"]

    t0 = time.monotonic()
    try:
        import subprocess

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 2)
        latency_ms = (time.monotonic() - t0) * 1000
        ok = result.returncode == 0
        return {"ok": ok, "error": result.stderr.strip() or None, "latency_ms": round(latency_ms, 1)}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "latency_ms": None}
