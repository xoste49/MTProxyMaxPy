"""Detection and import of legacy bash-based MTProxyMaxPy configuration files.

Legacy formats
--------------
settings.conf   KEY='VALUE'  or  KEY="VALUE"  shell assignments
secrets.conf    pipe-delimited, 9 columns:
                LABEL|KEY|CREATED_TS|ENABLED|MAX_CONNS|MAX_IPS|QUOTA_BYTES|EXPIRES|NOTES
upstreams.conf  pipe-delimited, 8 columns:
                NAME|TYPE|ADDR|USER|PASS|WEIGHT|IFACE|ENABLED
instances.conf  pipe-delimited, format varies but at minimum:
                NAME|PORT|ENABLED|NOTES
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from mtproxymaxpy.constants import (
    INSTALL_DIR,
    LEGACY_INSTANCES_FILE,
    LEGACY_SECRETS_FILE,
    LEGACY_SETTINGS_FILE,
    LEGACY_UPSTREAMS_FILE,
    LEGACY_BASH_SETTINGS_FILE,
    LEGACY_BASH_SECRETS_FILE,
    LEGACY_BASH_UPSTREAMS_FILE,
    LEGACY_BASH_INSTANCES_FILE,
    SETTINGS_FILE,
    SECRETS_FILE,
    UPSTREAMS_FILE,
    INSTANCES_FILE,
)
from mtproxymaxpy.config.settings import Settings
from mtproxymaxpy.config.secrets import Secret
from mtproxymaxpy.config.upstreams import Upstream
from mtproxymaxpy.config.instances import Instance

# ── Known settings.conf key → Settings field mapping ────────────────────────

_SETTINGS_KEY_MAP: dict[str, str] = {
    "PROXY_PORT": "proxy_port",
    "PROXY_METRICS_PORT": "proxy_metrics_port",
    "PROXY_DOMAIN": "proxy_domain",
    "PROXY_CONCURRENCY": "proxy_concurrency",
    "PROXY_CPUS": "proxy_cpus",
    "PROXY_MEMORY": "proxy_memory",
    "CUSTOM_IP": "custom_ip",
    "FAKE_CERT_LEN": "fake_cert_len",
    "PROXY_PROTOCOL": "proxy_protocol",
    "PROXY_PROTOCOL_TRUSTED_CIDRS": "proxy_protocol_trusted_cidrs",
    "AD_TAG": "ad_tag",
    "GEOBLOCK_MODE": "geoblock_mode",
    "BLOCKLIST_COUNTRIES": "blocklist_countries",
    "MASKING_ENABLED": "masking_enabled",
    "MASKING_HOST": "masking_host",
    "MASKING_PORT": "masking_port",
    "UNKNOWN_SNI_ACTION": "unknown_sni_action",
    "TELEGRAM_ENABLED": "telegram_enabled",
    "TELEGRAM_BOT_TOKEN": "telegram_bot_token",
    "TELEGRAM_CHAT_ID": "telegram_chat_id",
    "TELEGRAM_INTERVAL": "telegram_interval",
    "TELEGRAM_ALERTS_ENABLED": "telegram_alerts_enabled",
    "TELEGRAM_SERVER_LABEL": "telegram_server_label",
    "AUTO_UPDATE_ENABLED": "auto_update_enabled",
}

_BOOL_TRUE = {"true", "1", "yes"}
_BOOL_FALSE = {"false", "0", "no"}

_KV_RE = re.compile(r'^([A-Z_][A-Z0-9_]*)=["\']?(.*?)["\']?\s*(?:#.*)?$')


def _parse_bool(v: str) -> bool:
    lv = v.lower()
    if lv in _BOOL_TRUE:
        return True
    if lv in _BOOL_FALSE:
        return False
    raise ValueError(f"Cannot parse boolean: {v!r}")


def _parse_settings_conf(path: Path) -> dict[str, Any]:
    """Parse KEY='VALUE' shell-format settings.conf into a plain dict."""
    result: dict[str, Any] = {}
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _KV_RE.match(line)
        if not m:
            continue
        bash_key, raw_value = m.group(1), m.group(2)
        py_key = _SETTINGS_KEY_MAP.get(bash_key)
        if py_key is None:
            continue  # unknown key — skip silently

        # Type coercion based on the Pydantic model field type
        try:
            field_info = Settings.model_fields[py_key]
            annotation = field_info.annotation
            # unwrap Optional
            origin = getattr(annotation, "__origin__", None)
            args = getattr(annotation, "__args__", ())
            inner = args[0] if origin is type(None).__class__ and args else annotation

            if inner is bool or annotation is bool:
                result[py_key] = _parse_bool(raw_value)
            elif inner is int or annotation is int:
                result[py_key] = int(raw_value)
            else:
                result[py_key] = raw_value
        except Exception:
            result[py_key] = raw_value  # store as string, let Pydantic validate later

    return result


def _ts_to_date(ts: str) -> str:
    """Convert a Unix timestamp string to YYYY-MM-DD, or return '' on failure."""
    try:
        return datetime.fromtimestamp(int(ts)).date().isoformat()
    except Exception:
        return ""


def _parse_secrets_conf(path: Path) -> list[Secret]:
    """Parse pipe-delimited secrets.conf (9 columns)."""
    items: list[Secret] = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cols = line.split("|")
        if len(cols) < 2:
            continue
        # pad to 9
        cols += [""] * (9 - len(cols))
        label, key, created_ts, enabled, max_conns, max_ips, quota, expires, notes = cols[:9]
        try:
            items.append(Secret(
                label=label.strip(),
                key=key.strip(),
                created=_ts_to_date(created_ts.strip()) or created_ts.strip(),
                enabled=_parse_bool(enabled.strip()) if enabled.strip() else True,
                max_conns=int(max_conns.strip() or 0),
                max_ips=int(max_ips.strip() or 0),
                quota_bytes=int(quota.strip() or 0),
                expires=expires.strip() if expires.strip() not in ("", "0") else "",
                notes=notes.strip(),
            ))
        except Exception:
            continue
    return items


def _parse_upstreams_conf(path: Path) -> list[Upstream]:
    """Parse pipe-delimited upstreams.conf (8 columns)."""
    items: list[Upstream] = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cols = line.split("|")
        if len(cols) < 2:
            continue
        cols += [""] * (8 - len(cols))
        name, utype, addr, user, password, weight, iface, enabled = cols[:8]
        try:
            items.append(Upstream(
                name=name.strip(),
                type=utype.strip() or "direct",  # type: ignore[arg-type]
                addr=addr.strip(),
                user=user.strip(),
                password=password.strip(),
                weight=int(weight.strip() or 100),
                iface=iface.strip(),
                enabled=_parse_bool(enabled.strip()) if enabled.strip() else True,
            ))
        except Exception:
            continue
    return items


def _parse_instances_conf(path: Path) -> list[Instance]:
    """Parse pipe-delimited instances.conf (4 columns)."""
    items: list[Instance] = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cols = line.split("|")
        if len(cols) < 2:
            continue
        cols += [""] * (4 - len(cols))
        name, port, enabled, notes = cols[:4]
        try:
            items.append(Instance(
                name=name.strip(),
                port=int(port.strip()),
                enabled=_parse_bool(enabled.strip()) if enabled.strip() else True,
                notes=notes.strip(),
            ))
        except Exception:
            continue
    return items


# ── Public API ────────────────────────────────────────────────────────────────

@dataclass
class MigrationResult:
    settings_imported: bool = False
    secrets_count: int = 0
    upstreams_count: int = 0
    instances_count: int = 0
    skipped_keys: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def detect_legacy(install_dir: Path = INSTALL_DIR) -> dict[str, Path]:
    """Return a dict of legacy config files that exist.

    Keys are one of: 'settings', 'secrets', 'upstreams', 'instances'.
    Values are the resolved Path objects.
    Checks both /opt/mtproxymaxpy/ (same-dir copy) and /opt/mtproxymax/ (original bash dir).
    """
    # For each key, prefer the copy-in-place path, fall back to the original bash dir
    candidates: dict[str, list[Path]] = {
        "settings": [LEGACY_SETTINGS_FILE, LEGACY_BASH_SETTINGS_FILE],
        "secrets":  [LEGACY_SECRETS_FILE,  LEGACY_BASH_SECRETS_FILE],
        "upstreams": [LEGACY_UPSTREAMS_FILE, LEGACY_BASH_UPSTREAMS_FILE],
        "instances": [LEGACY_INSTANCES_FILE, LEGACY_BASH_INSTANCES_FILE],
    }
    result: dict[str, Path] = {}
    for key, paths in candidates.items():
        for p in paths:
            if p.exists():
                result[key] = p
                break
    return result


def run_migration(
    files: dict[str, Path] | None = None,
    *,
    settings_out: Path = SETTINGS_FILE,
    secrets_out: Path = SECRETS_FILE,
    upstreams_out: Path = UPSTREAMS_FILE,
    instances_out: Path = INSTANCES_FILE,
) -> MigrationResult:
    """Import legacy config files into the new TOML/JSON format.

    *files* should be the return value of :func:`detect_legacy`.
    If None, :func:`detect_legacy` is called automatically.
    """
    from mtproxymaxpy.config.settings import save_settings
    from mtproxymaxpy.config.secrets import save_secrets
    from mtproxymaxpy.config.upstreams import save_upstreams
    from mtproxymaxpy.config.instances import save_instances

    if files is None:
        files = detect_legacy()

    result = MigrationResult()

    if "settings" in files:
        try:
            raw = _parse_settings_conf(files["settings"])
            settings = Settings.model_validate(raw)
            save_settings(settings, settings_out)
            result.settings_imported = True
        except Exception as exc:
            result.errors.append(f"settings: {exc}")

    if "secrets" in files:
        try:
            items = _parse_secrets_conf(files["secrets"])
            save_secrets(items, secrets_out)
            result.secrets_count = len(items)
        except Exception as exc:
            result.errors.append(f"secrets: {exc}")

    if "upstreams" in files:
        try:
            items = _parse_upstreams_conf(files["upstreams"])
            save_upstreams(items, upstreams_out)
            result.upstreams_count = len(items)
        except Exception as exc:
            result.errors.append(f"upstreams: {exc}")

    if "instances" in files:
        try:
            items = _parse_instances_conf(files["instances"])
            save_instances(items, instances_out)
            result.instances_count = len(items)
        except Exception as exc:
            result.errors.append(f"instances: {exc}")

    return result
