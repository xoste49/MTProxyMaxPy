"""User secrets — Pydantic model + JSON persistence."""

from __future__ import annotations

import csv
import io
import json
import os
import secrets
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from mtproxymaxpy.constants import SECRETS_FILE


class Secret(BaseModel):
    label: str
    key: str = Field(default_factory=lambda: secrets.token_hex(16))
    created: str = Field(default_factory=lambda: datetime.now(tz=UTC).date().isoformat())
    enabled: bool = True
    max_conns: int = Field(0, ge=0)  # 0 = unlimited
    max_ips: int = Field(0, ge=0)  # 0 = unlimited
    quota_bytes: int = Field(0, ge=0)  # 0 = unlimited
    expires: str = ""  # normalized to YYYY-MM-DD or ""
    notes: str = ""

    @field_validator("expires", mode="before")
    @classmethod
    def _normalize_expires(cls, value: object) -> str:
        # Accept legacy values (e.g. "0") and normalize to a single internal format.
        if value is None:
            return ""
        raw = str(value).strip()
        if raw in ("", "0"):
            return ""

        # Primary format used by UI/CLI.
        try:
            return date.fromisoformat(raw).isoformat()
        except ValueError:
            pass

        # Accept datetime-like input (including RFC 3339 "Z") and reduce to date.
        dt_raw = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        try:
            return datetime.fromisoformat(dt_raw).date().isoformat()
        except ValueError:
            return ""


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


# ── Toggle ─────────────────────────────────────────────────────────────────────


def enable_secret(label: str, path: Path = SECRETS_FILE) -> Secret:
    """Enable a secret by label."""
    return _set_field(label, "enabled", value=True, path=path)


def disable_secret(label: str, path: Path = SECRETS_FILE) -> Secret:
    """Disable a secret by label."""
    return _set_field(label, "enabled", value=False, path=path)


def _set_field(label: str, field: str, *, value: bool | str, path: Path = SECRETS_FILE) -> Secret:
    items = load_secrets(path)
    for i, s in enumerate(items):
        if s.label == label:
            items[i] = s.model_copy(update={field: value})
            save_secrets(items, path)
            return items[i]
    raise KeyError(f"Secret {label!r} not found")


# ── Limits ─────────────────────────────────────────────────────────────────────


def set_secret_limits(
    label: str,
    *,
    max_conns: int | None = None,
    max_ips: int | None = None,
    quota_bytes: int | None = None,
    expires: str | None = None,
    path: Path = SECRETS_FILE,
) -> Secret:
    """Update per-user limit fields for an existing secret."""
    items = load_secrets(path)
    for i, s in enumerate(items):
        if s.label == label:
            updates: dict[str, Any] = {}
            if max_conns is not None:
                updates["max_conns"] = max_conns
            if max_ips is not None:
                updates["max_ips"] = max_ips
            if quota_bytes is not None:
                updates["quota_bytes"] = quota_bytes
            if expires is not None:
                updates["expires"] = expires
            items[i] = s.model_copy(update=updates)
            save_secrets(items, path)
            return items[i]
    raise KeyError(f"Secret {label!r} not found")


# ── Extend expiry ──────────────────────────────────────────────────────────────


def extend_secret(label: str, days: int, path: Path = SECRETS_FILE) -> Secret:
    """Extend a secret's expiry by *days* days.

    If the secret has no expiry, extends from today.
    """
    items = load_secrets(path)
    for i, s in enumerate(items):
        if s.label == label:
            if s.expires:
                base = date.fromisoformat(s.expires)
            else:
                base = datetime.now(tz=UTC).date()
            new_expires = (base + timedelta(days=days)).isoformat()
            items[i] = s.model_copy(update={"expires": new_expires})
            save_secrets(items, path)
            return items[i]
    raise KeyError(f"Secret {label!r} not found")


def bulk_extend_secrets(days: int, path: Path = SECRETS_FILE) -> list[Secret]:
    """Extend expiry of all secrets by *days* days."""
    items = load_secrets(path)
    updated = []
    for i, s in enumerate(items):
        base = date.fromisoformat(s.expires) if s.expires else datetime.now(tz=UTC).date()
        items[i] = s.model_copy(update={"expires": (base + timedelta(days=days)).isoformat()})
        updated.append(items[i])
    save_secrets(items, path)
    return updated


# ── Note ───────────────────────────────────────────────────────────────────────


def set_secret_note(label: str, text: str, path: Path = SECRETS_FILE) -> Secret:
    """Set or clear the notes field for a secret."""
    return _set_field(label, "notes", value=text, path=path)


# ── Rename / clone ─────────────────────────────────────────────────────────────


def rename_secret(old_label: str, new_label: str, path: Path = SECRETS_FILE) -> Secret:
    """Rename a secret (label only; key unchanged)."""
    items = load_secrets(path)
    if any(s.label == new_label for s in items):
        raise ValueError(f"Secret with label {new_label!r} already exists")
    for i, s in enumerate(items):
        if s.label == old_label:
            items[i] = s.model_copy(update={"label": new_label})
            save_secrets(items, path)
            return items[i]
    raise KeyError(f"Secret {old_label!r} not found")


def clone_secret(src_label: str, new_label: str, path: Path = SECRETS_FILE) -> Secret:
    """Clone a secret with a new label and a fresh random key."""
    items = load_secrets(path)
    if any(s.label == new_label for s in items):
        raise ValueError(f"Secret with label {new_label!r} already exists")
    for s in items:
        if s.label == src_label:
            new_s = s.model_copy(
                update={
                    "label": new_label,
                    "key": secrets.token_hex(16),
                    "created": datetime.now(tz=UTC).date().isoformat(),
                },
            )
            items.append(new_s)
            save_secrets(items, path)
            return new_s
    raise KeyError(f"Secret {src_label!r} not found")


# ── Expiry helpers ─────────────────────────────────────────────────────────────


def get_expired_secrets(path: Path = SECRETS_FILE) -> list[Secret]:
    """Return all secrets whose expiry date has passed."""
    today = datetime.now(tz=UTC).date().isoformat()
    return [s for s in load_secrets(path) if s.expires and s.expires < today]


def disable_expired_secrets(path: Path = SECRETS_FILE) -> list[Secret]:
    """Disable all expired secrets. Returns the list of newly-disabled ones."""
    items = load_secrets(path)
    today = datetime.now(tz=UTC).date().isoformat()
    changed: list[Secret] = []
    for i, s in enumerate(items):
        if s.enabled and s.expires and s.expires < today:
            items[i] = s.model_copy(update={"enabled": False})
            changed.append(items[i])
    if changed:
        save_secrets(items, path)
    return changed


# ── Export / import ────────────────────────────────────────────────────────────

_CSV_FIELDS = (
    "label",
    "key",
    "created",
    "enabled",
    "max_conns",
    "max_ips",
    "quota_bytes",
    "expires",
    "notes",
)


def export_secrets_csv(path: Path = SECRETS_FILE) -> str:
    """Return a CSV string of all secrets suitable for saving or printing."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(_CSV_FIELDS))
    writer.writeheader()
    for s in load_secrets(path):
        row = s.model_dump()
        writer.writerow({k: row[k] for k in _CSV_FIELDS})
    return buf.getvalue()


def import_secrets_csv(
    text: str,
    path: Path = SECRETS_FILE,
    *,
    overwrite: bool = False,
) -> list[Secret]:
    """Parse a CSV string and merge secrets into the store.

    If *overwrite* is False, secrets with duplicate labels are skipped.
    Returns a list of newly-added Secret objects.
    """
    existing = load_secrets(path)
    existing_labels = {s.label for s in existing}
    added: list[Secret] = []

    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        label = row.get("label", "").strip()
        if not label:
            continue
        if label in existing_labels and not overwrite:
            continue
        # Build Secret, falling back to defaults for missing fields
        s = Secret(
            label=label,
            key=row.get("key") or secrets.token_hex(16),
            created=row.get("created") or datetime.now(tz=UTC).date().isoformat(),
            enabled=(row.get("enabled", "true").lower() in ("1", "true", "yes")),
            max_conns=int(row.get("max_conns") or 0),
            max_ips=int(row.get("max_ips") or 0),
            quota_bytes=int(row.get("quota_bytes") or 0),
            expires=row.get("expires", ""),
            notes=row.get("notes", ""),
        )
        if label in existing_labels:
            # Replace existing
            existing = [s if s2.label != label else s for s2 in existing]
        else:
            existing.append(s)
        existing_labels.add(label)
        added.append(s)

    save_secrets(existing, path)
    return added
