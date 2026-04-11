"""Typer CLI entry-point for non-interactive use."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from mtproxymaxpy.constants import VERSION

app = typer.Typer(
    name="mtproxymaxpy",
    help="MTProxyMaxPy — Telegram MTProto proxy management",
    no_args_is_help=False,
    add_completion=False,
)


# ── install ────────────────────────────────────────────────────────────────────

@app.command()
def install(
    port: Annotated[int, typer.Option("--port", "-p", help="Proxy listen port")] = 443,
    domain: Annotated[str, typer.Option(help="FakeTLS domain")] = "cloudflare.com",
    systemd: Annotated[bool, typer.Option(help="Install systemd service")] = True,
) -> None:
    """Download telemt binary and set up the proxy."""
    from mtproxymaxpy.utils.system import check_root, check_dependencies
    from mtproxymaxpy.config.settings import Settings, save_settings
    from mtproxymaxpy import process_manager

    check_root()
    check_dependencies()

    typer.echo(f"[*] MTProxyMaxPy {VERSION} — installer")

    settings = Settings(proxy_port=port, proxy_domain=domain)
    save_settings(settings)
    typer.echo("[+] Settings saved.")

    typer.echo("[*] Downloading telemt binary…")
    process_manager.download_binary()
    typer.echo("[+] Binary ready.")

    if systemd:
        from mtproxymaxpy import systemd as svc
        try:
            svc.install()
            typer.echo("[+] systemd service installed and started.")
        except RuntimeError as exc:
            typer.echo(f"[!] systemd not available: {exc}", err=True)

    typer.echo("[+] Installation complete. Run 'mtproxymaxpy status' to verify.")


# ── start / stop / restart ─────────────────────────────────────────────────────

@app.command()
def start(
    no_tui: Annotated[bool, typer.Option("--no-tui", hidden=True)] = False,
) -> None:
    """Start the proxy."""
    from mtproxymaxpy import process_manager
    from mtproxymaxpy.utils.network import get_public_ip

    ip = get_public_ip() or ""
    pid = process_manager.start(public_ip=ip)
    typer.echo(f"[+] telemt started (PID {pid})")


@app.command()
def stop(
    no_tui: Annotated[bool, typer.Option("--no-tui", hidden=True)] = False,
) -> None:
    """Stop the proxy."""
    from mtproxymaxpy import process_manager

    process_manager.stop()
    typer.echo("[+] telemt stopped.")


@app.command()
def restart(
    no_tui: Annotated[bool, typer.Option("--no-tui", hidden=True)] = False,
) -> None:
    """Restart the proxy."""
    from mtproxymaxpy import process_manager
    from mtproxymaxpy.utils.network import get_public_ip

    ip = get_public_ip() or ""
    pid = process_manager.restart(public_ip=ip)
    typer.echo(f"[+] telemt restarted (PID {pid})")


# ── status ─────────────────────────────────────────────────────────────────────

@app.command()
def status() -> None:
    """Show proxy status."""
    from mtproxymaxpy import process_manager

    st = process_manager.status()
    icon = "●" if st["running"] else "○"
    typer.echo(f"{icon} telemt  running={st['running']}  pid={st['pid']}  "
               f"binary={'yes' if st['binary_present'] else 'no'}")


# ── update ─────────────────────────────────────────────────────────────────────

@app.command()
def update() -> None:
    """Download the latest telemt binary and restart the proxy."""
    from mtproxymaxpy import process_manager
    from mtproxymaxpy.utils.network import get_public_ip

    was_running = process_manager.is_running()
    if was_running:
        process_manager.stop()

    latest = process_manager.get_latest_version()
    typer.echo(f"[*] Downloading telemt {latest}…")
    process_manager.download_binary(version=latest, force=True)
    typer.echo("[+] Binary updated.")

    if was_running:
        ip = get_public_ip() or ""
        pid = process_manager.start(public_ip=ip)
        typer.echo(f"[+] telemt restarted (PID {pid})")


# ── secrets ────────────────────────────────────────────────────────────────────

secrets_app = typer.Typer(help="Manage user secrets", no_args_is_help=True)
app.add_typer(secrets_app, name="secret")


@secrets_app.command("add")
def secret_add(
    label: Annotated[str, typer.Argument(help="Human-readable label")],
    max_conns: Annotated[int, typer.Option(help="Max concurrent connections (0=unlimited)")] = 0,
    max_ips: Annotated[int, typer.Option(help="Max source IPs (0=unlimited)")] = 0,
    quota: Annotated[int, typer.Option(help="Traffic quota in bytes (0=unlimited)")] = 0,
    expires: Annotated[str, typer.Option(help="Expiry date YYYY-MM-DD")] = "",
    notes: Annotated[str, typer.Option()] = "",
) -> None:
    """Add a new user secret."""
    from mtproxymaxpy.config.secrets import add_secret

    try:
        s = add_secret(label, max_conns=max_conns, max_ips=max_ips, quota_bytes=quota,
                       expires=expires, notes=notes)
        typer.echo(f"[+] Secret '{s.label}' created: {s.key}")
    except ValueError as exc:
        typer.echo(f"[!] {exc}", err=True)
        raise typer.Exit(1)


@secrets_app.command("list")
def secret_list() -> None:
    """List all user secrets."""
    from mtproxymaxpy.config.secrets import load_secrets

    items = load_secrets()
    if not items:
        typer.echo("No secrets configured.")
        return
    for s in items:
        flag = "✓" if s.enabled else "✗"
        typer.echo(f"  {flag} {s.label:<20} {s.key}  (expires: {s.expires or 'never'})")


@secrets_app.command("remove")
def secret_remove(
    label: Annotated[str, typer.Argument()],
) -> None:
    """Remove a user secret by label."""
    from mtproxymaxpy.config.secrets import remove_secret

    if remove_secret(label):
        typer.echo(f"[+] Secret '{label}' removed.")
    else:
        typer.echo(f"[!] Secret '{label}' not found.", err=True)
        raise typer.Exit(1)


@secrets_app.command("rotate")
def secret_rotate(
    label: Annotated[str, typer.Argument()],
) -> None:
    """Generate a new key for an existing secret."""
    from mtproxymaxpy.config.secrets import rotate_secret

    try:
        s = rotate_secret(label)
        typer.echo(f"[+] New key for '{s.label}': {s.key}")
    except KeyError as exc:
        typer.echo(f"[!] {exc}", err=True)
        raise typer.Exit(1)


# ── upstreams ──────────────────────────────────────────────────────────────────

upstream_app = typer.Typer(help="Manage upstream SOCKS proxies", no_args_is_help=True)
app.add_typer(upstream_app, name="upstream")


@upstream_app.command("add")
def upstream_add(
    name: Annotated[str, typer.Argument()],
    addr: Annotated[str, typer.Option(help="host:port")] = "",
    type_: Annotated[str, typer.Option("--type", help="direct|socks5|socks4")] = "socks5",
    user: Annotated[str, typer.Option()] = "",
    password: Annotated[str, typer.Option()] = "",
    weight: Annotated[int, typer.Option(help="Weight 1-100")] = 100,
) -> None:
    """Add an upstream proxy."""
    from mtproxymaxpy.config.upstreams import Upstream, load_upstreams, save_upstreams

    items = load_upstreams()
    if any(u.name == name for u in items):
        typer.echo(f"[!] Upstream '{name}' already exists.", err=True)
        raise typer.Exit(1)
    items.append(Upstream(name=name, type=type_, addr=addr, user=user,  # type: ignore[arg-type]
                          password=password, weight=weight))
    save_upstreams(items)
    typer.echo(f"[+] Upstream '{name}' added.")


@upstream_app.command("list")
def upstream_list() -> None:
    """List all upstreams."""
    from mtproxymaxpy.config.upstreams import load_upstreams

    items = load_upstreams()
    if not items:
        typer.echo("No upstreams configured.")
        return
    for u in items:
        flag = "✓" if u.enabled else "✗"
        typer.echo(f"  {flag} {u.name:<20} {u.type}  {u.addr}  weight={u.weight}")


@upstream_app.command("remove")
def upstream_remove(name: Annotated[str, typer.Argument()]) -> None:
    """Remove an upstream by name."""
    from mtproxymaxpy.config.upstreams import load_upstreams, save_upstreams

    items = load_upstreams()
    new_items = [u for u in items if u.name != name]
    if len(new_items) == len(items):
        typer.echo(f"[!] Upstream '{name}' not found.", err=True)
        raise typer.Exit(1)
    save_upstreams(new_items)
    typer.echo(f"[+] Upstream '{name}' removed.")


# ── telegram-bot ───────────────────────────────────────────────────────────────

@app.command("telegram-bot")
def run_telegram_bot(
    no_tui: Annotated[bool, typer.Option("--no-tui", hidden=True)] = False,
) -> None:
    """Run the Telegram bot (blocking — intended for use by systemd)."""
    import signal as _signal
    from mtproxymaxpy import telegram_bot

    telegram_bot.start()
    typer.echo("[+] Telegram bot running. Press Ctrl+C to stop.")
    try:
        _signal.pause()
    except (KeyboardInterrupt, AttributeError):
        pass
    finally:
        telegram_bot.stop()


# ── version ────────────────────────────────────────────────────────────────────

@app.command()
def version() -> None:
    """Print the version and exit."""
    typer.echo(f"MTProxyMaxPy {VERSION}")
