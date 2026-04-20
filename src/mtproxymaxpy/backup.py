"""
Backup and restore of MTProxyMaxPy configuration files.

Creates/extracts .tar.gz archives containing settings, secrets, upstreams,
instances, and stats snapshots.  A metadata.json is always included.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import platform
import socket
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mtproxymaxpy.constants import (
    BACKUP_DIR,
    INSTALL_DIR,
    INSTANCES_FILE,
    SECRETS_FILE,
    SETTINGS_FILE,
    UPSTREAMS_FILE,
    VERSION,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _metadata() -> dict[str, Any]:
    now_utc = datetime.now(UTC)
    return {
        "version": VERSION,
        "date": now_utc.isoformat().replace("+00:00", "Z"),
        "hostname": socket.gethostname(),
        "platform": platform.system(),
    }


# ── Public API ─────────────────────────────────────────────────────────────────


def create_backup(label: str = "") -> Path:
    """Create a backup archive. Returns the path to the .tar.gz file."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    slug = f"-{label}" if label else ""
    archive_path = BACKUP_DIR / f"backup-{timestamp}{slug}.tar.gz"

    with tarfile.open(archive_path, "w:gz") as tf:
        # Config files
        for path in (SETTINGS_FILE, SECRETS_FILE, UPSTREAMS_FILE, INSTANCES_FILE):
            if path.exists():
                tf.add(path, arcname=path.name)

        # Stats snapshots
        stats_dir = INSTALL_DIR / "relay_stats"
        if stats_dir.exists():
            tf.add(stats_dir, arcname="relay_stats")

        # Metadata
        meta_bytes = json.dumps(_metadata(), indent=2).encode()
        info = tarfile.TarInfo("metadata.json")
        info.size = len(meta_bytes)
        tf.addfile(info, io.BytesIO(meta_bytes))

    archive_path.chmod(0o600)
    return archive_path


def list_backups() -> list[dict[str, Any]]:
    """Return a list of backup info dicts, sorted newest first."""
    if not BACKUP_DIR.exists():
        return []
    backups: list[dict[str, Any]] = []
    for f in BACKUP_DIR.glob("backup-*.tar.gz"):
        stat = f.stat()
        backups.append(
            {
                "path": f,
                "name": f.name,
                "size": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            },
        )
    return sorted(backups, key=lambda x: x["mtime"], reverse=True)


_CONFIG_EXTS = (".toml", ".json", ".conf")


def _extract_config_member(tf: tarfile.TarFile, member: tarfile.TarInfo, install_dir: Path) -> None:
    """Atomically extract a single config file member from a backup archive."""
    src = tf.extractfile(member)
    if src is None:
        return
    dest = install_dir / Path(member.name).name
    fd, tmp = tempfile.mkstemp(dir=install_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(src.read())
        Path(tmp).chmod(0o600)
        Path(tmp).replace(dest)
    except Exception:
        with contextlib.suppress(OSError):
            Path(tmp).unlink()
        raise


def restore_backup(archive: Path) -> dict[str, Any]:
    """
    Extract and restore a backup archive.

    Returns the metadata dict from the archive.
    Automatically creates a safety backup of the current state before restoring.
    """
    if not archive.exists():
        raise FileNotFoundError(f"Backup not found: {archive}")

    # Safety backup before overwriting anything
    pre_restore: Path | None = None
    if SETTINGS_FILE.exists() or SECRETS_FILE.exists():
        pre_restore = create_backup("pre-restore")

    meta: dict[str, Any] = {}
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive, "r:gz") as tf:
        # Read metadata
        try:
            meta_member = tf.getmember("metadata.json")
            src = tf.extractfile(meta_member)
            if src:
                meta = json.loads(src.read())
        except KeyError:
            pass

        for member in tf.getmembers():
            if member.name == "metadata.json":
                continue
            if any(member.name.endswith(ext) for ext in _CONFIG_EXTS):
                _extract_config_member(tf, member, INSTALL_DIR)
            elif member.isdir() and member.name == "relay_stats":
                (INSTALL_DIR / "relay_stats").mkdir(exist_ok=True)

    meta["pre_restore_backup"] = str(pre_restore) if pre_restore else None
    return meta
