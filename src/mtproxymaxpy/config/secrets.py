"""User secrets — Pydantic model + JSON persistence."""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from mtproxymaxpy.constants import SECRETS_FILE


class Secret(BaseModel):
    label: str
    key: str = Field(default_factory=lambda: secrets.token_hex(16))
    created: str = Field(default_factory=lambda: date.today().isoformat())
    enabled: bool = True
    max_conns: int = Field(0, ge=0)   # 0 = unlimited
    max_ips: int = Field(0, ge=0)     # 0 = unlimited
    quota_bytes: int = Field(0, ge=0) # 0 = unlimited
    expires: str = ""                  # YYYY-MM-DD or ""
    notes: str = ""


def load_secrets(path: Path = SECRETS_FILE) -> list[Secret]:
    """Load user secrets from a JSON file."""
    if not path.exists():
        return []
    with open(path) as fh:
        data = json.load(fh)
    return [Secret.model_validate(item) for item in data]


def save_secrets(items: list[Secret], path: Path = SECRETS_FILE) -> None:
    """Atomically write secrets to a JSON file (mode 600)."""
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


def add_secret(
    label: str,
    *,
    max_conns: int = 0,
    max_ips: int = 0,
    quota_bytes: int = 0,
    expires: str = "",
    notes: str = "",
    path: Path = SECRETS_FILE,
) -> Secret:
    """Create a new secret, persist it, and return it."""
    items = load_secrets(path)
    if any(s.label == label for s in items):
        raise ValueError(f"Secret with label {label!r} already exists")
    secret = Secret(
        label=label,
        max_conns=max_conns,
        max_ips=max_ips,
        quota_bytes=quota_bytes,
        expires=expires,
        notes=notes,
    )
    items.append(secret)
    save_secrets(items, path)
    return secret


def remove_secret(label: str, path: Path = SECRETS_FILE) -> bool:
    """Remove a secret by label. Returns True if found and removed."""
    items = load_secrets(path)
    new_items = [s for s in items if s.label != label]
    if len(new_items) == len(items):
        return False
    save_secrets(new_items, path)
    return True


def rotate_secret(label: str, path: Path = SECRETS_FILE) -> Secret:
    """Generate a new key for an existing secret."""
    items = load_secrets(path)
    for i, s in enumerate(items):
        if s.label == label:
            items[i] = s.model_copy(update={"key": secrets.token_hex(16)})
            save_secrets(items, path)
            return items[i]
    raise KeyError(f"Secret {label!r} not found")
