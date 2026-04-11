"""Multi-port instances — Pydantic model + JSON persistence."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from mtproxymaxpy.constants import INSTANCES_FILE


class Instance(BaseModel):
    name: str
    port: int = Field(..., ge=1, le=65535)
    enabled: bool = True
    notes: str = ""


def load_instances(path: Path = INSTANCES_FILE) -> list[Instance]:
    if not path.exists():
        return []
    with open(path) as fh:
        data = json.load(fh)
    return [Instance.model_validate(item) for item in data]


def save_instances(items: list[Instance], path: Path = INSTANCES_FILE) -> None:
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
