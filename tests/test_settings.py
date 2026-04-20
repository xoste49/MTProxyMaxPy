"""Tests for Settings persistence (round-trip TOML)."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from mtproxymaxpy.config.settings import Settings, load_settings, save_settings


def test_defaults_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    s = Settings()
    save_settings(s, path)
    loaded = load_settings(path)
    assert loaded == s


def test_custom_values_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    s = Settings(
        proxy_port=8443,
        proxy_domain="example.com",
        proxy_concurrency=4096,
        masking_enabled=False,
        telegram_enabled=True,
        telegram_bot_token="TOKEN123",
    )
    save_settings(s, path)
    loaded = load_settings(path)
    assert loaded.proxy_port == 8443
    assert loaded.proxy_domain == "example.com"
    assert loaded.proxy_concurrency == 4096
    assert loaded.masking_enabled is False
    assert loaded.telegram_enabled is True
    assert loaded.telegram_bot_token == "TOKEN123"


@pytest.mark.skipif(sys.platform == "win32", reason="Unix permissions not supported on Windows")
def test_file_has_mode_600(tmp_path: Path) -> None:

    path = tmp_path / "settings.toml"
    save_settings(Settings(), path)
    mode = path.stat().st_mode & 0o777
    assert mode == 0o600


def test_missing_file_returns_defaults(tmp_path: Path) -> None:
    path = tmp_path / "nonexistent.toml"
    s = load_settings(path)
    assert s == Settings()


def test_invalid_geoblock_mode() -> None:
    with pytest.raises(ValidationError):
        Settings(geoblock_mode="invalid")


def test_invalid_sni_action() -> None:
    with pytest.raises(ValidationError):
        Settings(unknown_sni_action="bogus")


def test_invalid_manager_update_branch() -> None:
    with pytest.raises(ValidationError):
        Settings(manager_update_branch="")
    with pytest.raises(ValidationError):
        Settings(manager_update_branch="feature branch")
