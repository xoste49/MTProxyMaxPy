"""Multi-port instances — Pydantic model + JSON persistence."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from mtproxymaxpy.constants import INSTANCES_FILE


class Instance(BaseModel):
    """Pydantic model representing a named proxy instance with a port and enabled flag."""

    name: str
    port: int = Field(..., ge=1, le=65535)
    enabled: bool = True
    notes: str = ""


def load_instances(path: Path = INSTANCES_FILE) -> list[Instance]:
    """Load instances from *path*; return an empty list if the file does not exist."""
    if not path.exists():
        return []
    with path.open() as fh:
        data = json.load(fh)
    return [Instance.model_validate(item) for item in data]


def save_instances(items: list[Instance], path: Path = INSTANCES_FILE) -> None:
    """Persist *items* to *path* using an atomic write (tempfile + replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [item.model_dump() for item in items]
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh, indent=2)
        Path(tmp).chmod(0o600)
        Path(tmp).replace(path)
    except Exception:
        with contextlib.suppress(OSError):
            Path(tmp).unlink()
        raise
