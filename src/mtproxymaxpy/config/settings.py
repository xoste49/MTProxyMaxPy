"""Global proxy settings — Pydantic model + TOML persistence."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

import tomllib
import tomli_w
from pydantic import BaseModel, Field, field_validator

from mtproxymaxpy.constants import (
    DEFAULT_CONCURRENCY,
    DEFAULT_DOMAIN,
    DEFAULT_FAKE_CERT_LEN,
    DEFAULT_MASKING_HOST,
    DEFAULT_MASKING_PORT,
    DEFAULT_METRICS_PORT,
    DEFAULT_PORT,
    DEFAULT_TELEGRAM_INTERVAL_HOURS,
    SETTINGS_FILE,
)


class Settings(BaseModel):
    # ── Proxy core ────────────────────────────────────────────────────────────
    proxy_port: int = Field(DEFAULT_PORT, ge=1, le=65535)
    proxy_metrics_port: int = Field(DEFAULT_METRICS_PORT, ge=1, le=65535)
    proxy_domain: str = DEFAULT_DOMAIN
    proxy_concurrency: int = Field(DEFAULT_CONCURRENCY, ge=1)
    proxy_cpus: str = ""
    proxy_memory: str = ""
    custom_ip: str = ""
    fake_cert_len: int = Field(DEFAULT_FAKE_CERT_LEN, ge=512)
    proxy_protocol: bool = False
    proxy_protocol_trusted_cidrs: str = ""

    # ── Ad-tag ────────────────────────────────────────────────────────────────
    ad_tag: str = ""

    # ── Geo-blocking ─────────────────────────────────────────────────────────
    geoblock_mode: str = "blacklist"
    blocklist_countries: str = ""

    # ── Traffic masking ───────────────────────────────────────────────────────
    masking_enabled: bool = True
    masking_host: str = DEFAULT_MASKING_HOST
    masking_port: int = Field(DEFAULT_MASKING_PORT, ge=1, le=65535)
    unknown_sni_action: str = "mask"

    # ── Telegram bot ─────────────────────────────────────────────────────────
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_interval: int = Field(DEFAULT_TELEGRAM_INTERVAL_HOURS, ge=1)
    telegram_alerts_enabled: bool = True
    telegram_server_label: str = "mtproxymaxpy"

    # ── Auto-update ───────────────────────────────────────────────────────────
    auto_update_enabled: bool = True

    @field_validator("geoblock_mode")
    @classmethod
    def _validate_geoblock_mode(cls, v: str) -> str:
        if v not in ("blacklist", "whitelist"):
            raise ValueError("geoblock_mode must be 'blacklist' or 'whitelist'")
        return v

    @field_validator("unknown_sni_action")
    @classmethod
    def _validate_sni_action(cls, v: str) -> str:
        if v not in ("mask", "drop"):
            raise ValueError("unknown_sni_action must be 'mask' or 'drop'")
        return v


def load_settings(path: Path = SETTINGS_FILE) -> Settings:
    """Load settings from a TOML file, returning defaults if missing."""
    if not path.exists():
        return Settings()
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    return Settings.model_validate(data)


def save_settings(settings: Settings, path: Path = SETTINGS_FILE) -> None:
    """Atomically write settings to a TOML file (mode 600)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = settings.model_dump()
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            tomli_w.dump(data, fh)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
