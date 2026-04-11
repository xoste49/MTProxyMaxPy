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
