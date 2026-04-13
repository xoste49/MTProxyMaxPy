"""Typer CLI entry-point for non-interactive use."""

from __future__ import annotations

import json
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

    # If legacy bash config exists, migrate it instead of using defaults
    from mtproxymaxpy.constants import SETTINGS_FILE
    from mtproxymaxpy.config.migration import detect_legacy, run_migration
    from mtproxymaxpy.config.settings import load_settings

    legacy = detect_legacy()
    if legacy and not SETTINGS_FILE.exists():
        typer.echo(f"[*] Legacy MTProxyMax config detected: {', '.join(legacy)}")
        typer.echo("[*] Migrating settings, secrets and upstreams…")
        result = run_migration(legacy)
        typer.echo(f"[+] Migration complete: {result.secrets_count} secret(s), {result.upstreams_count} upstream(s).")
        settings = load_settings()
    else:
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


# ── uninstall ──────────────────────────────────────────────────────────────────


@app.command()
def uninstall(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Stop and remove MTProxyMaxPy (stops proxy, removes systemd units, removes files)."""
    from mtproxymaxpy.utils.system import check_root

    check_root()
    if not yes:
        typer.confirm("This will stop the proxy and remove all installed files. Continue?", abort=True)

    from mtproxymaxpy import process_manager, systemd as svc
    from mtproxymaxpy.constants import INSTALL_DIR
    import shutil

    # Stop proxy
    if process_manager.is_running():
        typer.echo("[*] Stopping telemt…")
        process_manager.stop()

    # Remove systemd units
    try:
        svc.uninstall(telegram=True)
        typer.echo("[+] systemd services removed.")
    except Exception as exc:
        typer.echo(f"[!] systemd cleanup: {exc}", err=True)

    # Remove install directory
    if INSTALL_DIR.exists():
        typer.echo(f"[*] Removing {INSTALL_DIR}…")
        shutil.rmtree(INSTALL_DIR)

    typer.echo("[+] MTProxyMaxPy uninstalled.")


# ── start / stop / restart / reload ───────────────────────────────────────────


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


@app.command()
def reload() -> None:
    """Reload telemt config without restarting (SIGHUP)."""
    from mtproxymaxpy import process_manager

    process_manager.reload_config()
    typer.echo("[+] Config reloaded (SIGHUP sent).")


# ── status ─────────────────────────────────────────────────────────────────────


@app.command()
def status(
    output_json: Annotated[bool, typer.Option("--json", help="Output machine-readable JSON")] = False,
) -> None:
    """Show proxy status."""
    from mtproxymaxpy import process_manager, metrics as _metrics
    from mtproxymaxpy.config.settings import load_settings
    from mtproxymaxpy.config.secrets import load_secrets
    from mtproxymaxpy.utils.formatting import format_bytes, format_duration

    st = process_manager.status()
    settings = load_settings()
    secrets = load_secrets()
    mst = _metrics.get_stats()

    if output_json:
        data = {
            **st,
            "port": settings.proxy_port,
            "domain": settings.proxy_domain,
            "secrets_total": len(secrets),
            "secrets_enabled": sum(1 for s in secrets if s.enabled),
            "metrics": mst,
        }
        typer.echo(json.dumps(data, indent=2))
        return

    icon = "●" if st["running"] else "○"
    uptime = format_duration(st["uptime_sec"]) if st.get("uptime_sec") is not None else "?"
    typer.echo(
        f"{icon} telemt  running={st['running']}  pid={st['pid'] or '—'}  port={settings.proxy_port}  uptime={uptime}"
    )
    typer.echo(f"  secrets: {sum(1 for s in secrets if s.enabled)}/{len(secrets)} active")
    if mst.get("available"):
        typer.echo(
            f"  traffic: ↑{format_bytes(mst['bytes_out'])} ↓{format_bytes(mst['bytes_in'])}  "
            f"connections: {mst['active_connections']} active"
        )


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


# ── doctor ─────────────────────────────────────────────────────────────────────


@app.command()
def doctor() -> None:
    """Run comprehensive diagnostics and display results."""
    from mtproxymaxpy import doctor as _doctor

    results = _doctor.run_full_doctor()
    any_fail = False
    for r in results:
        ok = r.get("ok")
        if ok is True:
            icon, colour = "✓", "green"
        elif ok is False:
            icon, colour = "✗", "red"
            any_fail = True
        else:
            icon, colour = "?", "yellow"  # skipped / N/A
        name = r["name"]
        extras = {k: v for k, v in r.items() if k not in ("name", "ok")}
        detail = "  " + "  ".join(f"{k}={v}" for k, v in extras.items() if v is not None) if extras else ""
        typer.echo(f"  [{colour}]{icon}[/{colour}] {name}{detail}", color=True)  # type: ignore[call-arg]

    # Plain output for non-color terminals
    sys.stdout.flush()
    if any_fail:
        raise typer.Exit(1)


# ── health ─────────────────────────────────────────────────────────────────────


@app.command()
def health() -> None:
    """Quick health check — exits 0 if proxy is running, 1 otherwise."""
    from mtproxymaxpy import process_manager

    if process_manager.is_running():
        typer.echo("[+] healthy")
    else:
        typer.echo("[!] not running", err=True)
        raise typer.Exit(1)


# ── logs ──────────────────────────────────────────────────────────────────────


@app.command()
def logs(
    lines: Annotated[int, typer.Option("-n", help="Number of lines to show")] = 50,
    follow: Annotated[bool, typer.Option("-f", "--follow", help="Follow log output")] = False,
) -> None:
    """Show or follow the proxy log file."""
    from mtproxymaxpy.constants import INSTALL_DIR

    log_file = INSTALL_DIR / "telemt.log"
    if not log_file.exists():
        typer.echo("[!] Log file not found.", err=True)
        raise typer.Exit(1)

    if follow:
        import subprocess

        subprocess.run(["tail", "-f", str(log_file)])
    else:
        import subprocess

        subprocess.run(["tail", f"-{lines}", str(log_file)])


# ── metrics ────────────────────────────────────────────────────────────────────


@app.command()
def metrics() -> None:
    """Display live Prometheus metrics from the running proxy."""
    from mtproxymaxpy import metrics as _metrics
    from mtproxymaxpy.utils.formatting import format_bytes

    stats = _metrics.get_stats()
    if not stats.get("available"):
        typer.echo(f"[!] Metrics unavailable: {stats.get('error', 'proxy not running?')}", err=True)
        raise typer.Exit(1)

    typer.echo(f"  bytes_in:           {format_bytes(stats['bytes_in'])}")
    typer.echo(f"  bytes_out:          {format_bytes(stats['bytes_out'])}")
    typer.echo(f"  active_connections: {stats['active_connections']}")
    typer.echo(f"  total_connections:  {stats['total_connections']}")
    user_stats = stats.get("user_stats", {})
    if user_stats:
        typer.echo("\n  Per-user:")
        for key, us in user_stats.items():
            typer.echo(
                f"    {key[:12]}…  ↑{format_bytes(us.get('bytes_out', 0))}  "
                f"↓{format_bytes(us.get('bytes_in', 0))}  "
                f"active={int(us.get('active', 0))}"
            )


# ── traffic (alias of metrics) ─────────────────────────────────────────────────


@app.command()
def traffic() -> None:
    """Show traffic statistics (alias for 'metrics')."""
    metrics()


# ── connections ────────────────────────────────────────────────────────────────


@app.command()
def connections() -> None:
    """Show currently active connections."""
    from mtproxymaxpy import metrics as _metrics

    stats = _metrics.get_stats()
    if not stats.get("available"):
        typer.echo("[!] Metrics unavailable", err=True)
        raise typer.Exit(1)
    typer.echo(f"Active connections: {stats['active_connections']}")
    for key, us in stats.get("user_stats", {}).items():
        active = int(us.get("active", 0))
        if active:
            typer.echo(f"  {key[:12]}…  {active}")


# ── port ──────────────────────────────────────────────────────────────────────


@app.command()
def port(
    value: Annotated[Optional[int], typer.Argument(help="New port number, or omit to get")] = None,
) -> None:
    """Get or set the proxy listen port."""
    from mtproxymaxpy.config.settings import load_settings, save_settings

    settings = load_settings()
    if value is None:
        typer.echo(str(settings.proxy_port))
        return
    if not (1 <= value <= 65535):
        typer.echo("[!] Invalid port number", err=True)
        raise typer.Exit(1)
    save_settings(settings.model_copy(update={"proxy_port": value}))
    typer.echo(f"[+] Port set to {value}. Restart the proxy to apply.")


# ── domain ─────────────────────────────────────────────────────────────────────


@app.command()
def domain(
    value: Annotated[Optional[str], typer.Argument(help="New FakeTLS domain, 'get', or 'clear'")] = None,
) -> None:
    """Get, set, or clear the FakeTLS domain."""
    from mtproxymaxpy.config.settings import load_settings, save_settings

    settings = load_settings()
    if value is None or value == "get":
        typer.echo(settings.proxy_domain)
        return
    if value == "clear":
        save_settings(settings.model_copy(update={"proxy_domain": ""}))
        typer.echo("[+] Domain cleared.")
        return
    save_settings(settings.model_copy(update={"proxy_domain": value}))
    typer.echo(f"[+] Domain set to '{value}'. Restart the proxy to apply.")


# ── ip ─────────────────────────────────────────────────────────────────────────


@app.command()
def ip(
    value: Annotated[Optional[str], typer.Argument(help="New IP, 'get', or 'auto'")] = None,
) -> None:
    """Get, set, or auto-detect the public IP address."""
    from mtproxymaxpy.config.settings import load_settings, save_settings

    settings = load_settings()
    if value is None or value == "get":
        typer.echo(settings.custom_ip or "(auto)")
        return
    if value == "auto":
        save_settings(settings.model_copy(update={"custom_ip": ""}))
        typer.echo("[+] IP set to auto-detect.")
        return
    save_settings(settings.model_copy(update={"custom_ip": value}))
    typer.echo(f"[+] Custom IP set to '{value}'.")


# ── adtag ─────────────────────────────────────────────────────────────────────


@app.command()
def adtag(
    action: Annotated[str, typer.Argument(help="set <tag> | remove | view")] = "view",
    tag: Annotated[Optional[str], typer.Argument(help="Ad-tag value (for 'set')")] = None,
) -> None:
    """Get, set, or remove the Telegram ad-tag."""
    from mtproxymaxpy.config.settings import load_settings, save_settings

    settings = load_settings()
    if action == "view":
        typer.echo(settings.ad_tag or "(none)")
    elif action == "set":
        if not tag:
            typer.echo("[!] Provide a tag value after 'set'", err=True)
            raise typer.Exit(1)
        save_settings(settings.model_copy(update={"ad_tag": tag}))
        typer.echo(f"[+] Ad-tag set to '{tag}'.")
    elif action == "remove":
        save_settings(settings.model_copy(update={"ad_tag": ""}))
        typer.echo("[+] Ad-tag removed.")
    else:
        typer.echo(f"[!] Unknown action '{action}'. Use: set <tag> | remove | view", err=True)
        raise typer.Exit(1)


# ── sni-policy ────────────────────────────────────────────────────────────────


@app.command(name="sni-policy")
def sni_policy(
    value: Annotated[Optional[str], typer.Argument(help="mask | drop (omit to get)")] = None,
) -> None:
    """Get or set the unknown-SNI action (mask or drop)."""
    from mtproxymaxpy.config.settings import load_settings, save_settings

    settings = load_settings()
    if value is None:
        typer.echo(settings.unknown_sni_action)
        return
    if value not in ("mask", "drop"):
        typer.echo("[!] Value must be 'mask' or 'drop'", err=True)
        raise typer.Exit(1)
    save_settings(settings.model_copy(update={"unknown_sni_action": value}))
    typer.echo(f"[+] SNI policy set to '{value}'.")


# ── secrets ────────────────────────────────────────────────────────────────────

secrets_app = typer.Typer(help="Manage user secrets", no_args_is_help=True)
app.add_typer(secrets_app, name="secret")


@secrets_app.command("add")
def secret_add(
    label: Annotated[str, typer.Argument(help="Human-readable label")],
    max_conns: Annotated[int, typer.Option(help="Max concurrent connections (0=unlimited)")] = 0,
    max_ips: Annotated[int, typer.Option(help="Max source IPs (0=unlimited)")] = 0,
    quota: Annotated[str, typer.Option(help="Traffic quota e.g. 5G (0=unlimited)")] = "0",
    expires: Annotated[str, typer.Option(help="Expiry date YYYY-MM-DD")] = "",
    notes: Annotated[str, typer.Option()] = "",
    no_restart: Annotated[bool, typer.Option("--no-restart", help="Don't restart proxy after adding")] = False,
) -> None:
    """Add a new user secret."""
    from mtproxymaxpy.config.secrets import add_secret
    from mtproxymaxpy.utils.validation import parse_human_bytes

    quota_bytes = parse_human_bytes(quota) if quota != "0" else 0
    try:
        s = add_secret(
            label, max_conns=max_conns, max_ips=max_ips, quota_bytes=quota_bytes, expires=expires, notes=notes
        )
        typer.echo(f"[+] Secret '{s.label}' created: {s.key}")
        if not no_restart:
            _restart_if_running()
    except ValueError as exc:
        typer.echo(f"[!] {exc}", err=True)
        raise typer.Exit(1)


@secrets_app.command("add-batch")
def secret_add_batch(
    labels: Annotated[list[str], typer.Argument(help="Labels to add")],
) -> None:
    """Add multiple secrets with a single proxy restart."""
    from mtproxymaxpy.config.secrets import add_secret

    for label in labels:
        s = add_secret(label)
        typer.echo(f"[+] {s.label}: {s.key}")
    _restart_if_running()


@secrets_app.command("list")
def secret_list() -> None:
    """List all user secrets."""
    from mtproxymaxpy.config.secrets import load_secrets
    from mtproxymaxpy.utils.formatting import format_bytes

    items = load_secrets()
    if not items:
        typer.echo("No secrets configured.")
        return
    for s in items:
        flag = "✓" if s.enabled else "✗"
        limits = []
        if s.max_conns:
            limits.append(f"conns≤{s.max_conns}")
        if s.max_ips:
            limits.append(f"ips≤{s.max_ips}")
        if s.quota_bytes:
            limits.append(f"quota={format_bytes(s.quota_bytes)}")
        limit_str = "  " + " ".join(limits) if limits else ""
        typer.echo(f"  {flag} {s.label:<22} {s.key}  expires={s.expires or 'never'}{limit_str}")


@secrets_app.command("remove")
def secret_remove(
    label: Annotated[str, typer.Argument()],
    no_restart: Annotated[bool, typer.Option("--no-restart")] = False,
) -> None:
    """Remove a user secret by label."""
    from mtproxymaxpy.config.secrets import remove_secret

    if remove_secret(label):
        typer.echo(f"[+] Secret '{label}' removed.")
        if not no_restart:
            _restart_if_running()
    else:
        typer.echo(f"[!] Secret '{label}' not found.", err=True)
        raise typer.Exit(1)


@secrets_app.command("rotate")
def secret_rotate(
    label: Annotated[str, typer.Argument()],
    no_restart: Annotated[bool, typer.Option("--no-restart")] = False,
) -> None:
    """Generate a new key for an existing secret."""
    from mtproxymaxpy.config.secrets import rotate_secret

    try:
        s = rotate_secret(label)
        typer.echo(f"[+] New key for '{s.label}': {s.key}")
        if not no_restart:
            _restart_if_running()
    except KeyError as exc:
        typer.echo(f"[!] {exc}", err=True)
        raise typer.Exit(1)


@secrets_app.command("enable")
def secret_enable(label: Annotated[str, typer.Argument()]) -> None:
    """Enable a secret."""
    from mtproxymaxpy.config.secrets import enable_secret

    enable_secret(label)
    typer.echo(f"[+] Enabled '{label}'.")
    _restart_if_running()


@secrets_app.command("disable")
def secret_disable(label: Annotated[str, typer.Argument()]) -> None:
    """Disable a secret (without removing it)."""
    from mtproxymaxpy.config.secrets import disable_secret

    disable_secret(label)
    typer.echo(f"[+] Disabled '{label}'.")
    _restart_if_running()


@secrets_app.command("limits")
def secret_limits(label: Annotated[str, typer.Argument()]) -> None:
    """Show per-user limits for a secret."""
    from mtproxymaxpy.config.secrets import load_secrets
    from mtproxymaxpy.utils.formatting import format_bytes

    items = load_secrets()
    s = next((x for x in items if x.label == label), None)
    if s is None:
        typer.echo(f"[!] Not found: '{label}'", err=True)
        raise typer.Exit(1)
    typer.echo(f"  label:         {s.label}")
    typer.echo(f"  max_conns:     {s.max_conns or 'unlimited'}")
    typer.echo(f"  max_ips:       {s.max_ips or 'unlimited'}")
    typer.echo(f"  quota:         {format_bytes(s.quota_bytes) if s.quota_bytes else 'unlimited'}")
    typer.echo(f"  expires:       {s.expires or 'never'}")
    typer.echo(f"  notes:         {s.notes or ''}")


@secrets_app.command("setlimit")
def secret_setlimit(
    label: Annotated[str, typer.Argument()],
    field: Annotated[str, typer.Argument(help="conns | ips | quota | expires")],
    value: Annotated[str, typer.Argument()],
) -> None:
    """Set a single limit field for a secret."""
    from mtproxymaxpy.config.secrets import set_secret_limits
    from mtproxymaxpy.utils.validation import parse_human_bytes

    kwargs: dict = {}
    if field == "conns":
        kwargs["max_conns"] = int(value)
    elif field == "ips":
        kwargs["max_ips"] = int(value)
    elif field == "quota":
        kwargs["quota_bytes"] = parse_human_bytes(value)
    elif field == "expires":
        kwargs["expires"] = value
    else:
        typer.echo(f"[!] Unknown field '{field}'. Use: conns | ips | quota | expires", err=True)
        raise typer.Exit(1)
    set_secret_limits(label, **kwargs)
    typer.echo(f"[+] Updated {field} for '{label}'.")
    _restart_if_running()


@secrets_app.command("extend")
def secret_extend(
    label: Annotated[str, typer.Argument()],
    days: Annotated[int, typer.Argument(help="Days to add")],
) -> None:
    """Extend a secret's expiry by N days."""
    from mtproxymaxpy.config.secrets import extend_secret

    s = extend_secret(label, days)
    typer.echo(f"[+] New expiry for '{label}': {s.expires}")


@secrets_app.command("bulk-extend")
def secret_bulk_extend(
    days: Annotated[int, typer.Argument(help="Days to add to all secrets")],
) -> None:
    """Extend the expiry of all secrets by N days."""
    from mtproxymaxpy.config.secrets import bulk_extend_secrets

    changed = bulk_extend_secrets(days)
    typer.echo(f"[+] Extended {len(changed)} secrets by {days} days.")


@secrets_app.command("disable-expired")
def secret_disable_expired() -> None:
    """Disable all secrets whose expiry date has passed."""
    from mtproxymaxpy.config.secrets import disable_expired_secrets

    changed = disable_expired_secrets()
    typer.echo(f"[+] Disabled {len(changed)} expired secret(s).")
    if changed:
        _restart_if_running()


@secrets_app.command("rename")
def secret_rename(
    old_label: Annotated[str, typer.Argument()],
    new_label: Annotated[str, typer.Argument()],
) -> None:
    """Rename a secret (label only; key unchanged)."""
    from mtproxymaxpy.config.secrets import rename_secret

    rename_secret(old_label, new_label)
    typer.echo(f"[+] Renamed '{old_label}' → '{new_label}'.")


@secrets_app.command("clone")
def secret_clone(
    src_label: Annotated[str, typer.Argument()],
    new_label: Annotated[str, typer.Argument()],
) -> None:
    """Clone a secret with a new label and fresh key."""
    from mtproxymaxpy.config.secrets import clone_secret

    s = clone_secret(src_label, new_label)
    typer.echo(f"[+] Cloned '{src_label}' → '{new_label}': {s.key}")
    _restart_if_running()


@secrets_app.command("note")
def secret_note(
    label: Annotated[str, typer.Argument()],
    text: Annotated[str, typer.Argument(help="Note text (empty to clear)")] = "",
) -> None:
    """Set or clear the note for a secret."""
    from mtproxymaxpy.config.secrets import set_secret_note

    set_secret_note(label, text)
    typer.echo(f"[+] Note updated for '{label}'.")


@secrets_app.command("link")
def secret_link(
    label: Annotated[Optional[str], typer.Argument(help="Label (omit for first enabled)")] = None,
) -> None:
    """Print the proxy link (tg:// and https://) for a secret."""
    from mtproxymaxpy.config.secrets import load_secrets
    from mtproxymaxpy.config.settings import load_settings
    from mtproxymaxpy.utils.network import get_public_ip
    from mtproxymaxpy.utils.proxy_link import build_proxy_links

    secs = load_secrets()
    if label:
        s = next((x for x in secs if x.label == label), None)
    else:
        s = next((x for x in secs if x.enabled), None)
    if s is None:
        typer.echo("[!] No matching secret found.", err=True)
        raise typer.Exit(1)
    settings = load_settings()
    srv = settings.custom_ip or get_public_ip() or "YOUR_SERVER_IP"
    tg, web = build_proxy_links(s.key, settings.proxy_domain, srv, settings.proxy_port)
    typer.echo(f"  tg://    {tg}")
    typer.echo(f"  https    {web}")


@secrets_app.command("qr")
def secret_qr(
    label: Annotated[Optional[str], typer.Argument()] = None,
) -> None:
    """Print an ASCII QR code for a secret's proxy link."""
    from mtproxymaxpy.config.secrets import load_secrets
    from mtproxymaxpy.config.settings import load_settings
    from mtproxymaxpy.utils.network import get_public_ip
    from mtproxymaxpy.utils.proxy_link import build_proxy_links, render_qr_terminal

    secs = load_secrets()
    s = next((x for x in secs if not label or x.label == label), None)
    if s is None:
        typer.echo("[!] No matching secret.", err=True)
        raise typer.Exit(1)
    settings = load_settings()
    srv = settings.custom_ip or get_public_ip() or "YOUR_SERVER_IP"
    _, web = build_proxy_links(s.key, settings.proxy_domain, srv, settings.proxy_port)
    qr = render_qr_terminal(web)
    if qr:
        typer.echo(qr)
    else:
        typer.echo(f"[!] Install qrcode to render QR. Link: {web}", err=True)


@secrets_app.command("stats")
def secret_stats() -> None:
    """Show per-user traffic stats from the Prometheus endpoint."""
    from mtproxymaxpy.config.secrets import load_secrets
    from mtproxymaxpy import metrics as _metrics
    from mtproxymaxpy.utils.formatting import format_bytes

    mst = _metrics.get_stats()
    secs = load_secrets()
    key_to_label = {s.key: s.label for s in secs}

    if not mst.get("available"):
        typer.echo(f"[!] Metrics unavailable: {mst.get('error')}", err=True)
        raise typer.Exit(1)

    header = f"  {'Label':<22} {'Key':<14} {'In':>10} {'Out':>10} {'Active':>8}"
    typer.echo(header)
    typer.echo("  " + "-" * (len(header) - 2))
    for key, us in mst.get("user_stats", {}).items():
        label = key_to_label.get(key, key[:12] + "…")
        typer.echo(
            f"  {label:<22} {key[:12] + '…':<14} "
            f"{format_bytes(us.get('bytes_in', 0)):>10} "
            f"{format_bytes(us.get('bytes_out', 0)):>10} "
            f"{int(us.get('active', 0)):>8}"
        )


@secrets_app.command("reset-traffic")
def secret_reset_traffic(
    label: Annotated[Optional[str], typer.Argument(help="Label, or omit for all")] = None,
) -> None:
    """Reset traffic accounting snapshots for a secret (or all)."""
    from mtproxymaxpy.constants import STATS_DIR

    if not STATS_DIR.exists():
        typer.echo("[!] Stats directory not found.", err=True)
        raise typer.Exit(1)
    if label is None:
        files = list(STATS_DIR.glob("*.json"))
    else:
        from mtproxymaxpy.config.secrets import load_secrets

        secs = load_secrets()
        s = next((x for x in secs if x.label == label), None)
        if s is None:
            typer.echo(f"[!] Secret '{label}' not found.", err=True)
            raise typer.Exit(1)
        files = list(STATS_DIR.glob(f"{s.key}*.json"))
    for f in files:
        f.unlink(missing_ok=True)
    typer.echo(f"[+] Reset traffic for {len(files)} file(s).")


@secrets_app.command("export")
def secret_export() -> None:
    """Export all secrets as CSV to stdout."""
    from mtproxymaxpy.config.secrets import export_secrets_csv

    typer.echo(export_secrets_csv(), nl=False)


@secrets_app.command("import")
def secret_import(
    file: Annotated[typer.FileText, typer.Argument(help="CSV file path or - for stdin")] = sys.stdin,  # type: ignore[assignment]
    overwrite: Annotated[bool, typer.Option(help="Overwrite existing entries")] = False,
) -> None:
    """Import secrets from a CSV file (as produced by 'secret export')."""
    from mtproxymaxpy.config.secrets import import_secrets_csv

    text = file.read()
    added = import_secrets_csv(text, overwrite=overwrite)
    typer.echo(f"[+] Imported {len(added)} secret(s).")
    if added:
        _restart_if_running()


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
    weight: Annotated[int, typer.Option(help="Weight 1-100")] = 10,
) -> None:
    """Add an upstream proxy."""
    from mtproxymaxpy.config.upstreams import add_upstream

    add_upstream(name, type_=type_, addr=addr, user=user, password=password, weight=weight)
    typer.echo(f"[+] Upstream '{name}' added.")
    _restart_if_running()


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
        typer.echo(f"  {flag} {u.name:<20} {u.type}  {u.addr or '(direct)'}  weight={u.weight}")


@upstream_app.command("remove")
def upstream_remove(name: Annotated[str, typer.Argument()]) -> None:
    """Remove an upstream by name."""
    from mtproxymaxpy.config.upstreams import remove_upstream

    remove_upstream(name)
    typer.echo(f"[+] Upstream '{name}' removed.")
    _restart_if_running()


@upstream_app.command("enable")
def upstream_enable(name: Annotated[str, typer.Argument()]) -> None:
    """Enable an upstream."""
    from mtproxymaxpy.config.upstreams import enable_upstream

    enable_upstream(name)
    typer.echo(f"[+] Enabled '{name}'.")
    _restart_if_running()


@upstream_app.command("disable")
def upstream_disable(name: Annotated[str, typer.Argument()]) -> None:
    """Disable an upstream."""
    from mtproxymaxpy.config.upstreams import disable_upstream

    disable_upstream(name)
    typer.echo(f"[+] Disabled '{name}'.")
    _restart_if_running()


@upstream_app.command("test")
def upstream_test(name: Annotated[str, typer.Argument()]) -> None:
    """Test connectivity through an upstream."""
    from mtproxymaxpy.config.upstreams import test_upstream

    typer.echo(f"  Testing '{name}'…")
    result = test_upstream(name)
    if result.get("ok"):
        lat = result.get("latency_ms")
        typer.echo(f"[+] OK{f'  ({lat} ms)' if lat else ''}")
    else:
        typer.echo(f"[!] FAIL: {result.get('error')}", err=True)
        raise typer.Exit(1)


# ── backup ─────────────────────────────────────────────────────────────────────

backup_app = typer.Typer(help="Backup and restore configuration", no_args_is_help=True)
app.add_typer(backup_app, name="backup")


@backup_app.command("create")
def backup_create(
    label: Annotated[str, typer.Argument(help="Optional label for the backup")] = "",
) -> None:
    """Create a new backup archive."""
    from mtproxymaxpy import backup as _backup

    path = _backup.create_backup(label)
    typer.echo(f"[+] Backup created: {path}")


@backup_app.command("list")
def backup_list() -> None:
    """List all available backups."""
    from mtproxymaxpy import backup as _backup
    from mtproxymaxpy.utils.formatting import format_bytes

    backups = _backup.list_backups()
    if not backups:
        typer.echo("No backups found.")
        return
    for b in backups:
        typer.echo(f"  {b['mtime'].strftime('%Y-%m-%d %H:%M')}  {format_bytes(b['size']):<10}  {b['name']}")


@backup_app.command("restore")
def backup_restore(
    archive: Annotated[str, typer.Argument(help="Backup filename or full path")],
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    """Restore from a backup archive."""
    from mtproxymaxpy import backup as _backup
    from mtproxymaxpy.constants import BACKUP_DIR

    path = Path(archive) if "/" in archive or "\\" in archive else BACKUP_DIR / archive
    if not yes:
        typer.confirm(f"Restore from '{path.name}'? Current config will be backed up.", abort=True)
    meta = _backup.restore_backup(path)
    typer.echo(f"[+] Restored. Original: {meta.get('version', '?')} / {meta.get('date', '?')}")
    if meta.get("pre_restore_backup"):
        typer.echo(f"    Pre-restore safety backup: {meta['pre_restore_backup']}")


# ── geoblock ───────────────────────────────────────────────────────────────────

geo_app = typer.Typer(help="Geo-blocking via iptables + ipset", no_args_is_help=True)
app.add_typer(geo_app, name="geoblock")


@geo_app.command("add")
def geoblock_add(
    cc: Annotated[str, typer.Argument(help="ISO 3166-1 alpha-2 country code e.g. RU")],
) -> None:
    """Block a country (downloads CIDRs and applies iptables rules)."""
    from mtproxymaxpy import geoblock

    typer.echo(f"[*] Applying geo-block for {cc.upper()}…")
    n = geoblock.add_country(cc)
    typer.echo(f"[+] Blocked {cc.upper()} ({n} CIDRs).")


@geo_app.command("remove")
def geoblock_remove(cc: Annotated[str, typer.Argument()]) -> None:
    """Remove geo-block for a country."""
    from mtproxymaxpy import geoblock

    geoblock.remove_country(cc)
    typer.echo(f"[+] Removed geo-block for {cc.upper()}.")


@geo_app.command("list")
def geoblock_list() -> None:
    """List currently geo-blocked countries."""
    from mtproxymaxpy import geoblock

    countries = geoblock.list_countries()
    if countries:
        typer.echo("  Blocked: " + ", ".join(countries))
    else:
        typer.echo("  No countries currently geo-blocked.")


@geo_app.command("clear")
def geoblock_clear(
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    """Remove all geo-block rules."""
    from mtproxymaxpy import geoblock

    if not yes:
        typer.confirm("Remove all geo-block rules?", abort=True)
    geoblock.clear_all()
    typer.echo("[+] All geo-block rules removed.")


# ── telegram ───────────────────────────────────────────────────────────────────

telegram_app = typer.Typer(help="Telegram bot management", no_args_is_help=True)
app.add_typer(telegram_app, name="telegram")


@telegram_app.command("status")
def telegram_status() -> None:
    """Show Telegram bot configuration and service status."""
    from mtproxymaxpy.config.settings import load_settings

    settings = load_settings()
    typer.echo(f"  enabled:       {settings.telegram_enabled}")
    typer.echo(f"  token set:     {bool(settings.telegram_bot_token)}")
    typer.echo(f"  chat_id:       {settings.telegram_chat_id or '(not set)'}")
    typer.echo(f"  interval (h):  {settings.telegram_interval}")
    typer.echo(f"  alerts:        {settings.telegram_alerts_enabled}")
    typer.echo(f"  server label:  {settings.telegram_server_label}")
    typer.echo(f"  backend:       {getattr(settings, 'telegram_backend', 'aiogram')}")


@telegram_app.command("test")
def telegram_test() -> None:
    """Send a test message to the configured Telegram chat."""
    from mtproxymaxpy.config.settings import load_settings
    import telebot

    settings = load_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        typer.echo("[!] Bot token or chat ID not configured.", err=True)
        raise typer.Exit(1)
    bot = telebot.TeleBot(settings.telegram_bot_token)
    bot.send_message(settings.telegram_chat_id, "✅ MTProxyMaxPy test message — bot is working!")
    typer.echo("[+] Test message sent.")


@telegram_app.command("disable")
def telegram_disable() -> None:
    """Disable the Telegram bot."""
    from mtproxymaxpy.config.settings import load_settings, save_settings

    settings = load_settings()
    save_settings(settings.model_copy(update={"telegram_enabled": False}))
    typer.echo("[+] Telegram bot disabled.")


@telegram_app.command("enable")
def telegram_enable() -> None:
    """Enable the Telegram bot."""
    from mtproxymaxpy.config.settings import load_settings, save_settings

    settings = load_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        typer.echo("[!] Configure token and chat_id first.", err=True)
        raise typer.Exit(1)
    save_settings(settings.model_copy(update={"telegram_enabled": True}))
    typer.echo("[+] Telegram bot enabled.")


@telegram_app.command("backend")
def telegram_backend(
    value: Annotated[Optional[str], typer.Argument(help="Backend name: pytelegrambotapi|aiogram")] = None,
) -> None:
    """Get or set Telegram backend implementation."""
    from mtproxymaxpy.config.settings import load_settings, save_settings

    settings = load_settings()
    current = getattr(settings, "telegram_backend", "aiogram")
    if value is None:
        typer.echo(current)
        return

    if value not in ("pytelegrambotapi", "aiogram"):
        typer.echo("[!] Backend must be 'pytelegrambotapi' or 'aiogram'.", err=True)
        raise typer.Exit(1)

    save_settings(settings.model_copy(update={"telegram_backend": value}))
    typer.echo(f"[+] Telegram backend set to {value}.")


# ── telegram-bot (systemd daemon entry) ───────────────────────────────────────


@app.command("telegram-bot")
def run_telegram_bot(
    no_tui: Annotated[bool, typer.Option("--no-tui", hidden=True)] = False,
) -> None:
    """Run the Telegram bot (blocking — intended for use by systemd)."""
    import signal as _signal
    from mtproxymaxpy.config.settings import load_settings

    settings = load_settings()
    backend = getattr(settings, "telegram_backend", "aiogram")

    if backend == "aiogram":
        from mtproxymaxpy import telegram_bot_aiogram as telegram_backend
    else:
        from mtproxymaxpy import telegram_bot as telegram_backend

    telegram_backend.start()
    typer.echo(f"[+] Telegram bot running ({backend}). Press Ctrl+C to stop.")
    try:
        _signal.pause()
    except (KeyboardInterrupt, AttributeError):
        pass
    finally:
        telegram_backend.stop()


# ── version ────────────────────────────────────────────────────────────────────


@app.command()
def version() -> None:
    """Print the version and exit."""
    typer.echo(f"MTProxyMaxPy {VERSION}")


# ── Internal helpers ───────────────────────────────────────────────────────────


def _restart_if_running() -> None:
    """Regenerate config and restart the proxy if it's currently running."""
    from mtproxymaxpy import process_manager
    from mtproxymaxpy.utils.network import get_public_ip

    if process_manager.is_running():
        ip = get_public_ip() or ""
        pid = process_manager.restart(public_ip=ip)
        typer.echo(f"[*] Proxy restarted (PID {pid})")
    else:
        # Regenerate config even if not running so it's ready on next start
        try:
            process_manager.write_toml_config()
        except Exception:
            pass
