"""Tests for legacy bash config migration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtproxymaxpy.config.migration import (
    _parse_secrets_conf,
    _parse_settings_conf,
    _parse_upstreams_conf,
    detect_legacy,
    run_migration,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

# ── detect_legacy ─────────────────────────────────────────────────────────────


def test_detect_legacy_empty(tmp_path: Path) -> None:
    result = detect_legacy(tmp_path)
    assert result == {}


def test_detect_legacy_finds_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings_file = tmp_path / "settings.conf"
    secrets_file = tmp_path / "secrets.conf"
    settings_file.write_text("PROXY_PORT='443'\n")
    secrets_file.write_text("")

    # Patch the constants so detect_legacy looks in tmp_path
    import mtproxymaxpy.config.migration as mod
    import mtproxymaxpy.constants as c

    monkeypatch.setattr(c, "LEGACY_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(c, "LEGACY_SECRETS_FILE", secrets_file)
    monkeypatch.setattr(c, "LEGACY_UPSTREAMS_FILE", tmp_path / "upstreams.conf")
    monkeypatch.setattr(c, "LEGACY_INSTANCES_FILE", tmp_path / "instances.conf")
    monkeypatch.setattr(mod, "LEGACY_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(mod, "LEGACY_SECRETS_FILE", secrets_file)
    monkeypatch.setattr(mod, "LEGACY_UPSTREAMS_FILE", tmp_path / "upstreams.conf")
    monkeypatch.setattr(mod, "LEGACY_INSTANCES_FILE", tmp_path / "instances.conf")

    found = detect_legacy(tmp_path)
    assert "settings" in found
    assert "secrets" in found
    assert "upstreams" not in found


# ── _parse_settings_conf ──────────────────────────────────────────────────────


def _write(path: Path, text: str) -> Path:
    path.write_text(text)
    return path


def test_parse_settings_basic(tmp_path: Path) -> None:
    f = _write(tmp_path / "s.conf", "PROXY_PORT='8443'\nPROXY_DOMAIN='example.com'\n")
    result = _parse_settings_conf(f)
    assert result["proxy_port"] == 8443
    assert result["proxy_domain"] == "example.com"


def test_parse_settings_bool(tmp_path: Path) -> None:
    f = _write(tmp_path / "s.conf", "MASKING_ENABLED='false'\nTELEGRAM_ENABLED='true'\n")
    result = _parse_settings_conf(f)
    assert result["masking_enabled"] is False
    assert result["telegram_enabled"] is True


def test_parse_settings_ignores_unknown(tmp_path: Path) -> None:
    f = _write(tmp_path / "s.conf", "UNKNOWN_KEY='value'\nPROXY_PORT='443'\n")
    result = _parse_settings_conf(f)
    assert "unknown_key" not in result
    assert result["proxy_port"] == 443


def test_parse_settings_skips_comments(tmp_path: Path) -> None:
    f = _write(tmp_path / "s.conf", "# comment\nPROXY_PORT='9443'\n# more\n")
    result = _parse_settings_conf(f)
    assert result["proxy_port"] == 9443


# ── _parse_secrets_conf ───────────────────────────────────────────────────────


def test_parse_secrets_basic(tmp_path: Path) -> None:
    content = "alice|" + "a" * 32 + "|1700000000|true|0|0|0||notes\n"
    f = _write(tmp_path / "secrets.conf", content)
    items = _parse_secrets_conf(f)
    assert len(items) == 1
    assert items[0].label == "alice"
    assert items[0].key == "a" * 32
    assert items[0].enabled is True
    assert items[0].notes == "notes"


def test_parse_secrets_multiple(tmp_path: Path) -> None:
    lines = "\n".join(
        [
            "alice|" + "a" * 32 + "|0|true|0|0|0||",
            "bob|" + "b" * 32 + "|0|false|5|2|1000000||vip",
        ],
    )
    f = _write(tmp_path / "secrets.conf", lines)
    items = _parse_secrets_conf(f)
    assert len(items) == 2
    assert items[1].enabled is False
    assert items[1].max_conns == 5
    assert items[1].quota_bytes == 1000000


def test_parse_secrets_skips_empty_and_comments(tmp_path: Path) -> None:
    content = "# header\n\nalice|" + "a" * 32 + "|||||||"
    f = _write(tmp_path / "secrets.conf", content)
    items = _parse_secrets_conf(f)
    assert len(items) == 1


def test_parse_secrets_skips_bad_lines(tmp_path: Path) -> None:
    content = "onlyone\nalice|" + "a" * 32 + "|||||||"
    f = _write(tmp_path / "secrets.conf", content)
    items = _parse_secrets_conf(f)
    assert len(items) == 1  # "onlyone" has only 1 column → skip


# ── _parse_upstreams_conf ──────────────────────────────────────────────────────


def test_parse_upstreams_basic(tmp_path: Path) -> None:
    content = "warp|socks5|127.0.0.1:1080|user|pass|90|eth0|true\n"
    f = _write(tmp_path / "upstreams.conf", content)
    items = _parse_upstreams_conf(f)
    assert len(items) == 1
    u = items[0]
    assert u.name == "warp"
    assert u.type == "socks5"
    assert u.addr == "127.0.0.1:1080"
    assert u.weight == 90
    assert u.iface == "eth0"


def test_parse_upstreams_skips_bad(tmp_path: Path) -> None:
    content = "bad\nwarp|socks5|127.0.0.1:1080|||100||true\n"
    f = _write(tmp_path / "upstreams.conf", content)
    items = _parse_upstreams_conf(f)
    assert len(items) == 1


# ── run_migration ─────────────────────────────────────────────────────────────


def test_run_migration_full(tmp_path: Path) -> None:
    settings_src = _write(
        tmp_path / "settings.conf",
        "PROXY_PORT='7443'\nPROXY_DOMAIN='test.com'\n",
    )
    secrets_src = _write(
        tmp_path / "secrets.conf",
        "alice|" + "a" * 32 + "|||||||",
    )
    upstreams_src = _write(
        tmp_path / "upstreams.conf",
        "direct|direct||||100||true",
    )

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    result = run_migration(
        files={"settings": settings_src, "secrets": secrets_src, "upstreams": upstreams_src},
        settings_out=out_dir / "settings.toml",
        secrets_out=out_dir / "secrets.json",
        upstreams_out=out_dir / "upstreams.json",
        instances_out=out_dir / "instances.json",
    )

    assert result.settings_imported is True
    assert result.secrets_count == 1
    assert result.upstreams_count == 1
    assert result.errors == []

    # Verify output files
    from mtproxymaxpy.config.secrets import load_secrets
    from mtproxymaxpy.config.settings import load_settings

    s = load_settings(out_dir / "settings.toml")
    assert s.proxy_port == 7443
    assert s.proxy_domain == "test.com"

    secrets = load_secrets(out_dir / "secrets.json")
    assert secrets[0].label == "alice"


def test_run_migration_partial(tmp_path: Path) -> None:
    secrets_src = _write(
        tmp_path / "secrets.conf",
        "bob|" + "b" * 32 + "|||||||",
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    result = run_migration(
        files={"secrets": secrets_src},
        settings_out=out_dir / "settings.toml",
        secrets_out=out_dir / "secrets.json",
        upstreams_out=out_dir / "upstreams.json",
        instances_out=out_dir / "instances.json",
    )
    assert result.settings_imported is False
    assert result.secrets_count == 1


def test_run_migration_no_files(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    result = run_migration(
        files={},
        settings_out=out_dir / "settings.toml",
        secrets_out=out_dir / "secrets.json",
        upstreams_out=out_dir / "upstreams.json",
        instances_out=out_dir / "instances.json",
    )
    assert result.settings_imported is False
    assert result.secrets_count == 0
    assert result.errors == []
