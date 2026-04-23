"""
Smoke tests: every module must import cleanly and the CLI must be invocable.

These tests exist to catch NameError / ImportError / SyntaxError regressions
that surfaced during development (e.g. missing 'load_settings' import in cli.py).
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

# ── 1. All package modules import without error ───────────────────────────────

_SRC_ROOT = Path(__file__).parent.parent / "src" / "mtproxymaxpy"


# Collect every .py file under src/mtproxymaxpy/, convert to dotted module names.
def _module_names() -> list[str]:
    names: list[str] = []
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        rel = path.relative_to(_SRC_ROOT.parent)  # mtproxymaxpy/...
        mod = str(rel.with_suffix("")).replace("/", ".").replace("\\", ".")
        # skip __pycache__ and compiled artefacts
        if "__pycache__" in mod:
            continue
        # Legacy Textual modules are no longer used by the Rich TUI.
        if mod.startswith(("mtproxymaxpy.tui.screens.", "mtproxymaxpy.tui.widgets.")):
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
    import typer

    from mtproxymaxpy.cli import app

    click_app = typer.main.get_command(app)
    # Only include actual commands (not groups that are sub-apps)
    return [
        name
        for name, cmd in click_app.commands.items()  # type: ignore[attr-defined]
        if not hasattr(cmd, "commands")  # skip sub-groups like 'secret', 'upstream' etc.
    ]


def _cli_groups() -> list[tuple[str, str]]:
    """Return (group_name, sub_name) pairs for all sub-command groups."""
    import typer

    from mtproxymaxpy.cli import backup_app, geo_app, secrets_app, telegram_app, upstream_app

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
        pairs.extend(
            (group_name, sub_name)
            for sub_name in click_grp.commands  # type: ignore[attr-defined]
        )
    return pairs


@pytest.mark.parametrize("command", _cli_commands())
def test_top_level_help(command: str) -> None:
    """Every top-level command must respond to --help without crashing."""
    from typer.testing import CliRunner

    from mtproxymaxpy.cli import app

    runner = CliRunner()
    result = runner.invoke(app, [command, "--help"])
    assert result.exit_code == 0, f"'{command} --help' exited {result.exit_code}:\n{result.output}"


@pytest.mark.parametrize(("group", "command"), _cli_groups())
def test_subcommand_help(group: str, command: str) -> None:
    """Every sub-command must respond to --help without crashing."""
    from typer.testing import CliRunner

    from mtproxymaxpy.cli import app

    runner = CliRunner()
    result = runner.invoke(app, [group, command, "--help"])
    assert result.exit_code == 0, f"'{group} {command} --help' exited {result.exit_code}:\n{result.output}"


# ── 5. secret export / import CSV round-trip ─────────────────────────────────


def test_secret_csv_round_trip(tmp_path: Path) -> None:
    from mtproxymaxpy.config.secrets import (
        add_secret,
        export_secrets_csv,
        import_secrets_csv,
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
