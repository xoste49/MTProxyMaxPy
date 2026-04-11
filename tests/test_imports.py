"""Smoke tests: every module must import cleanly and the CLI must be invocable.

These tests exist to catch NameError / ImportError / SyntaxError regressions
that surfaced during development (e.g. missing 'load_settings' import in cli.py).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Generator

import pytest

# ── 1. All package modules import without error ───────────────────────────────

_SRC_ROOT = Path(__file__).parent.parent / "src" / "mtproxymaxpy"

# Collect every .py file under src/mtproxymaxpy/, convert to dotted module names.
def _module_names() -> list[str]:
    names: list[str] = []
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        rel = path.relative_to(_SRC_ROOT.parent)           # mtproxymaxpy/...
        mod = str(rel.with_suffix("")).replace("/", ".").replace("\\", ".")
        # skip __pycache__ and compiled artefacts
        if "__pycache__" in mod:
            continue
        names.append(mod)
    return names


@pytest.mark.parametrize("module", _module_names())
def test_module_imports(module: str) -> None:
    """Each module must be importable (no SyntaxError / NameError at import time)."""
    importlib.import_module(module)


# ── 2. CLI top-level app object is importable ─────────────────────────────────

def test_cli_app_importable() -> None:
    from mtproxymaxpy.cli import app  # noqa: F401  — must not raise


# ── 3. Every CLI command responds to --help without error ─────────────────────

def _cli_commands() -> list[str]:
    """Return the names of all registered top-level Typer commands via Click."""
    from mtproxymaxpy.cli import app
    import typer

    click_app = typer.main.get_command(app)
    # Only include actual commands (not groups that are sub-apps)
    return [
        name for name, cmd in click_app.commands.items()  # type: ignore[attr-defined]
        if not hasattr(cmd, "commands")  # skip sub-groups like 'secret', 'upstream' etc.
    ]


def _cli_groups() -> list[tuple[str, str]]:
    """Return (group_name, sub_name) pairs for all sub-command groups."""
    import typer
    from mtproxymaxpy.cli import app, secrets_app, upstream_app, backup_app, geo_app, telegram_app

    group_map = {
        "secret": secrets_app,
        "upstream": upstream_app,
        "backup": backup_app,
        "geoblock": geo_app,
        "telegram": telegram_app,
    }
    pairs: list[tuple[str, str]] = []
    for group_name, grp_app in group_map.items():
        click_grp = typer.main.get_command(grp_app)
        for sub_name in click_grp.commands:  # type: ignore[attr-defined]
            pairs.append((group_name, sub_name))
    return pairs


@pytest.mark.parametrize("command", _cli_commands())
def test_top_level_help(command: str) -> None:
    """Every top-level command must respond to --help without crashing."""
    from typer.testing import CliRunner
    from mtproxymaxpy.cli import app

    runner = CliRunner()
    result = runner.invoke(app, [command, "--help"])
    assert result.exit_code == 0, (
        f"'{command} --help' exited {result.exit_code}:\n{result.output}"
    )


@pytest.mark.parametrize("group,command", _cli_groups())
def test_subcommand_help(group: str, command: str) -> None:
    """Every sub-command must respond to --help without crashing."""
    from typer.testing import CliRunner
    from mtproxymaxpy.cli import app

    runner = CliRunner()
    result = runner.invoke(app, [group, command, "--help"])
    assert result.exit_code == 0, (
        f"'{group} {command} --help' exited {result.exit_code}:\n{result.output}"
    )


# ── 4. CLI install command runs migration without NameError ───────────────────

def test_install_runs_migration_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """install() migrates legacy config when settings.toml absent — no NameError."""
    import mtproxymaxpy.constants as _c

    # Point all paths to tmp_path so nothing actually writes to /opt/
    monkeypatch.setattr(_c, "INSTALL_DIR", tmp_path)
    monkeypatch.setattr(_c, "SETTINGS_FILE", tmp_path / "settings.toml")
    monkeypatch.setattr(_c, "SECRETS_FILE", tmp_path / "secrets.json")
    monkeypatch.setattr(_c, "UPSTREAMS_FILE", tmp_path / "upstreams.json")
    monkeypatch.setattr(_c, "INSTANCES_FILE", tmp_path / "instances.json")
    monkeypatch.setattr(_c, "TOML_CONFIG_FILE", tmp_path / "config.toml")

    # Write a minimal legacy secrets.conf so migration path is taken
    legacy_bash = tmp_path / "bash"
    legacy_bash.mkdir()
    (legacy_bash / "settings.conf").write_text("PROXY_PORT='8443'\n")
    (legacy_bash / "secrets.conf").write_text("testuser|" + "a" * 32 + "|0|1|0|0|0||\n")

    import mtproxymaxpy.config.migration as _mig
    monkeypatch.setattr(
        _mig, "LEGACY_BASH_SETTINGS_FILE", legacy_bash / "settings.conf"
    )
    monkeypatch.setattr(
        _mig, "LEGACY_BASH_SECRETS_FILE", legacy_bash / "secrets.conf"
    )
    monkeypatch.setattr(_mig, "LEGACY_BASH_UPSTREAMS_FILE", tmp_path / "no.conf")
    monkeypatch.setattr(_mig, "LEGACY_BASH_INSTANCES_FILE", tmp_path / "no.conf")
    monkeypatch.setattr(_mig, "LEGACY_SETTINGS_FILE", tmp_path / "no.conf")
    monkeypatch.setattr(_mig, "LEGACY_SECRETS_FILE", tmp_path / "no.conf")
    monkeypatch.setattr(_mig, "LEGACY_UPSTREAMS_FILE", tmp_path / "no.conf")
    monkeypatch.setattr(_mig, "LEGACY_INSTANCES_FILE", tmp_path / "no.conf")
    monkeypatch.setattr(_mig, "SETTINGS_FILE", tmp_path / "settings.toml")
    monkeypatch.setattr(_mig, "SECRETS_FILE", tmp_path / "secrets.json")
    monkeypatch.setattr(_mig, "UPSTREAMS_FILE", tmp_path / "upstreams.json")
    monkeypatch.setattr(_mig, "INSTANCES_FILE", tmp_path / "instances.json")

    import mtproxymaxpy.config.settings as _s
    monkeypatch.setattr(_s, "SETTINGS_FILE", tmp_path / "settings.toml")

    # Patch away external calls (root check, deps check, binary download, systemd)
    from mtproxymaxpy.utils import system as _sys_utils
    monkeypatch.setattr(_sys_utils, "check_root", lambda: None)
    monkeypatch.setattr(_sys_utils, "check_dependencies", lambda: None)

    import mtproxymaxpy.process_manager as _pm
    monkeypatch.setattr(_pm, "download_binary", lambda **kw: None)

    import mtproxymaxpy.systemd as _sd
    monkeypatch.setattr(_sd, "install", lambda **kw: None)

    from typer.testing import CliRunner
    from mtproxymaxpy.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["install", "--no-systemd"])
    assert result.exit_code == 0, f"install exited {result.exit_code}:\n{result.output}"
    assert "Migration complete" in result.output
    assert "NameError" not in result.output


# ── 5. secret export / import CSV round-trip ─────────────────────────────────

def test_secret_csv_round_trip(tmp_path: Path) -> None:
    from mtproxymaxpy.config.secrets import (
        add_secret, export_secrets_csv, import_secrets_csv, load_secrets,
    )

    secrets_file = tmp_path / "secrets.json"
    s = add_secret("roundtrip", path=secrets_file)
    csv_text = export_secrets_csv(path=secrets_file)
    assert "roundtrip" in csv_text

    secrets_file2 = tmp_path / "secrets2.json"
    imported = import_secrets_csv(csv_text, path=secrets_file2)
    assert len(imported) == 1
    assert imported[0].label == "roundtrip"
    assert imported[0].key == s.key


# ── 6. FakeTLS proxy link format ─────────────────────────────────────────────

def test_faketls_secret_format() -> None:
    from mtproxymaxpy.utils.proxy_link import build_faketls_secret, build_proxy_links

    key = "a" * 32
    domain = "cloudflare.com"
    secret = build_faketls_secret(key, domain)
    assert secret.startswith("ee")
    assert key in secret
    assert domain.encode().hex() in secret

    tg, web = build_proxy_links(key, domain, "1.2.3.4", 443)
    assert tg.startswith("tg://proxy")
    assert "1.2.3.4" in tg
    assert web.startswith("https://t.me/proxy")
