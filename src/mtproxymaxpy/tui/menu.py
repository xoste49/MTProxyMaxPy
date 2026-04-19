"""Rich-based interactive terminal menu for MTProxyMaxPy.

Replaces the Textual GUI-style app with a numbered-menu TUI similar to the
original bash script: box-drawing headers, coloured status, numbered choices.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import TYPE_CHECKING, Any

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from pathlib import Path
    from mtproxymaxpy.config.secrets import Secret
    from mtproxymaxpy.config.upstreams import Upstream

from mtproxymaxpy.constants import APP_TITLE, VERSION

logger = logging.getLogger(__name__)

console = Console(highlight=False)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _clear() -> None:
    console.clear()


def _pause() -> None:
    Prompt.ask("\n  [dim]Press Enter to continue…[/dim]", default="", console=console)


def _read_last_lines(path: Path, limit: int, max_bytes: int = 262_144) -> list[str]:
    """Read only tail lines from a potentially large log file.

    Limits bytes read from the end of file to avoid high memory usage in live screens.
    """
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            read_from = max(0, size - max_bytes)
            fh.seek(read_from)
            chunk = fh.read()
        lines = chunk.decode("utf-8", errors="replace").splitlines()
        if read_from > 0 and lines:
            # First line may be cut if we started in the middle of the file.
            lines = lines[1:]
        return lines[-limit:]
    except (OSError, ValueError):
        return []


def _header_panel() -> Panel:
    """Build the status header shown at the top of every screen."""
    lines: list[Text] = []
    tg_line = Text("○ TG UNKNOWN", style="dim")
    try:
        from mtproxymaxpy import metrics, process_manager
        from mtproxymaxpy.config.secrets import load_secrets
        from mtproxymaxpy.config.settings import load_settings
        from mtproxymaxpy.constants import SYSTEMD_TELEGRAM_SERVICE, SYSTEMD_UNIT_DIR
        from mtproxymaxpy.utils.formatting import format_bytes, format_duration

        st = process_manager.status()
        settings = load_settings()
        secrets = load_secrets()

        status_line = Text()
        if st.get("running"):
            status_line.append("● RUNNING", style="bold green")
        else:
            status_line.append("○ STOPPED", style="bold red")

        get_ver = getattr(process_manager, "get_binary_version", None)
        ver = "?"
        if callable(get_ver):
            try:
                ver = str(get_ver())
            except (OSError, subprocess.SubprocessError):
                ver = "?"
        status_line.append(f"  Engine: telemt v{ver}", style="cyan")
        lines.append(status_line)

        port = getattr(settings, "proxy_port", "?")
        domain = getattr(settings, "proxy_domain", "?")
        uptime = "-"
        if st.get("uptime_sec") is not None:
            uptime = format_duration(st["uptime_sec"])

        core_line = Text()
        core_line.append(f"Port: {port}", style="cyan")
        core_line.append(f"  Uptime: {uptime}", style="yellow")
        core_line.append(f"  Domain: {domain}", style="magenta")
        lines.append(core_line)

        traffic_line = Text()
        mst = metrics.get_stats(max_age=2.0)
        if mst.get("available"):
            traffic_line.append(
                f"Traffic: ↓ {format_bytes(int(mst.get('bytes_in', 0)))}  ↑ {format_bytes(int(mst.get('bytes_out', 0)))}",
                style="green",
            )
            traffic_line.append(f"  Conns: {int(mst.get('active_connections', 0))}", style="yellow")
        else:
            traffic_line.append("Traffic: ↓ 0 B  ↑ 0 B", style="dim")
            traffic_line.append("  Conns: 0", style="dim")
        lines.append(traffic_line)

        active = sum(1 for s in secrets if getattr(s, "enabled", False))
        disabled = max(0, len(secrets) - active)
        secrets_line = Text()
        secrets_line.append(f"Secrets: {active} active / {disabled} disabled", style="cyan")
        if st.get("pid"):
            secrets_line.append(f"  PID: {st['pid']}", style="dim")
        lines.append(secrets_line)

        if not getattr(settings, "telegram_enabled", False):
            tg_line = Text("○ TG DISABLED", style="bold red")
        else:
            service_unit = SYSTEMD_UNIT_DIR / f"{SYSTEMD_TELEGRAM_SERVICE}.service"
            if not service_unit.exists():
                tg_line = Text("◐ TG NOT INSTALLED", style="bold yellow")
            else:
                try:
                    from mtproxymaxpy import systemd as _systemd

                    if _systemd.is_active(SYSTEMD_TELEGRAM_SERVICE):
                        tg_line = Text("● TG RUNNING", style="bold green")
                    else:
                        tg_line = Text("○ TG STOPPED", style="bold red")
                except (OSError, RuntimeError, subprocess.SubprocessError):
                    tg_line = Text("○ TG UNKNOWN", style="dim")
    except (OSError, ValueError, RuntimeError):
        lines = [Text("○ UNKNOWN", style="dim")]

    combined = Text()
    for i, line in enumerate(lines):
        if i:
            combined.append("\n")
        combined.append_text(line)

    combined.append("\n")
    combined.append_text(tg_line)

    # Update badge
    try:
        from mtproxymaxpy.constants import UPDATE_BADGE_FILE

        if UPDATE_BADGE_FILE.exists():
            combined.append("\n")
            combined.append("⬆ Update available - select [10]", style="bold yellow")
    except (OSError, ValueError):
        logger.debug("Failed to read update badge", exc_info=True)

    title = f"[bold cyan]{APP_TITLE} v{VERSION}[/bold cyan]  [dim]Telegram MTProto Proxy Manager[/dim]"
    return Panel(combined, title=title, border_style="cyan", padding=(0, 2))


def _choice(n: int, label: str, hint: str = "") -> str:
    hint_part = f"  [dim]{hint}[/dim]" if hint else ""
    return f"  [bold cyan]{n}[/bold cyan]  {label}{hint_part}"


def _ask_choice(max_n: int, *, allow_zero: bool = True) -> int:
    """Prompt for a menu choice. Returns the integer selected."""
    zero_hint = "/0=back" if allow_zero else ""
    while True:
        raw = Prompt.ask(
            f"\n  [bold]Choice[/bold] [dim](1-{max_n}{zero_hint})[/dim]",
            default="0",
            console=console,
        )
        try:
            n = int(raw.strip())
            if (allow_zero and n == 0) or (1 <= n <= max_n):
                return n
        except ValueError:
            pass
        console.print("  [red]Invalid choice[/red]")


def _manager_update_branch() -> str:
    try:
        from mtproxymaxpy.config.settings import load_settings

        settings = load_settings()
        branch = str(getattr(settings, "manager_update_branch", "main") or "main").strip()
        if branch and not any(ch.isspace() for ch in branch):
            return branch
    except (OSError, ValueError):
        logger.debug("Failed to read update branch from settings", exc_info=True)
    return "main"


def _manager_commits_url(branch: str) -> str:
    from urllib.parse import quote

    from mtproxymaxpy.constants import GITHUB_API_COMMITS

    base = GITHUB_API_COMMITS.strip().rstrip("/")
    if base.rsplit("/", 1)[-1] == "commits":
        return f"{base}/{quote(branch, safe='')}"
    return f"{base.rsplit('/', 1)[0]}/{quote(branch, safe='')}"


# ── Background update checker ─────────────────────────────────────────────────


def _check_update_bg(wait_timeout: float = 3.0) -> None:
    """Fire a background thread to compare GitHub HEAD SHA with stored baseline.

    Args:
        wait_timeout: Maximum seconds to wait for the check to complete before returning (default: 3.0).
                      Prevents blocking the TUI startup while still ensuring the badge is set on first run.

    """
    import threading

    def _read_local_manager_sha() -> str:
        try:
            from mtproxymaxpy.constants import INSTALL_DIR, UPDATE_SHA_FILE

            res = subprocess.run(
                ["git", "-C", str(INSTALL_DIR), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            sha = (res.stdout or "").strip().lower()
            if res.returncode == 0 and len(sha) == 40 and all(c in "0123456789abcdef" for c in sha):
                return sha
            return UPDATE_SHA_FILE.read_text().strip().lower() if UPDATE_SHA_FILE.exists() else ""
        except (OSError, subprocess.SubprocessError):
            return ""

    def _worker() -> None:
        try:
            from mtproxymaxpy.constants import UPDATE_BADGE_FILE, UPDATE_SHA_FILE

            branch = _manager_update_branch()
            commits_url = _manager_commits_url(branch)

            resp = httpx.get(
                commits_url,
                headers={"Accept": "application/vnd.github.sha"},
                timeout=10,
                follow_redirects=True,
            )
            remote_sha = resp.text.strip()[:40].lower()
            if len(remote_sha) != 40 or not all(c in "0123456789abcdef" for c in remote_sha):
                return

            local_sha = _read_local_manager_sha()
            if not local_sha:
                # Fallback for non-git installs: keep baseline behavior from .update_sha.
                stored = UPDATE_SHA_FILE.read_text().strip().lower() if UPDATE_SHA_FILE.exists() else ""
                if not stored:
                    UPDATE_SHA_FILE.write_text(remote_sha)
                    UPDATE_BADGE_FILE.unlink(missing_ok=True)
                elif remote_sha != stored:
                    UPDATE_BADGE_FILE.write_text("new")
                else:
                    UPDATE_BADGE_FILE.unlink(missing_ok=True)
                return

            if remote_sha != local_sha:
                UPDATE_BADGE_FILE.write_text("new")
            else:
                UPDATE_BADGE_FILE.unlink(missing_ok=True)
        except (OSError, httpx.HTTPError, ValueError):
            logger.debug("Background update check failed", exc_info=True)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    # Wait up to wait_timeout seconds for the check to complete to ensure
    # the badge file is set on first menu render, avoiding the race condition
    # where the menu displays before the background check finishes.
    thread.join(timeout=wait_timeout)


# ── Main Menu ──────────────────────────────────────────────────────────────────


def run_tui() -> None:
    """Entry point: run the interactive menu (blocking)."""
    from mtproxymaxpy.constants import SETTINGS_FILE

    _check_update_bg()

    if not SETTINGS_FILE.exists():
        # Check for legacy bash config first
        migrated = False
        try:
            from mtproxymaxpy.config.migration import detect_legacy

            legacy = detect_legacy()
            if legacy:
                _migration_screen(legacy)
                migrated = True
        except (OSError, ImportError, ValueError):
            logger.debug("Legacy config migration failed", exc_info=True)
        # Fresh install — run setup wizard
        if not migrated:
            _setup_wizard()

    while True:
        _clear()
        console.print(_header_panel())
        console.print()

        try:
            from mtproxymaxpy import geoblock
            from mtproxymaxpy.config.secrets import load_secrets
            from mtproxymaxpy.config.settings import load_settings
            from mtproxymaxpy.config.upstreams import load_upstreams

            n_secrets = len(load_secrets())
            n_upstreams = len(load_upstreams())
            n_geo = len(geoblock.list_countries())
            settings = load_settings()
            tg_hint = "enabled" if settings.telegram_enabled else "disabled"
            cfg_hint = f"port {settings.proxy_port} · {settings.proxy_domain}"
        except (OSError, ValueError, RuntimeError):
            n_secrets = n_upstreams = n_geo = 0
            tg_hint = cfg_hint = ""

        try:
            from mtproxymaxpy.constants import UPDATE_BADGE_FILE

            update_hint = "[yellow]⬆ available![/yellow]" if UPDATE_BADGE_FILE.exists() else ""
        except (OSError, ValueError):
            update_hint = ""

        console.print(
            _choice(1, "Proxy Management"),
            _choice(2, "Secrets Management", f"{n_secrets} user(s)"),
            _choice(3, "Share Links & QR"),
            _choice(4, "Upstream Proxies", f"{n_upstreams} upstream(s)"),
            _choice(5, "Configuration", cfg_hint),
            _choice(6, "Logs & Traffic"),
            _choice(7, "Security / Geo-blocking", f"{n_geo} country/ies"),
            _choice(8, "Backup & Restore"),
            _choice(9, "Telegram Bot", tg_hint),
            _choice(10, "Update", update_hint),
            sep="\n",
        )
        choice = _ask_choice(10)
        {
            1: _proxy_menu,
            2: _secrets_menu,
            3: _links_menu,
            4: _upstreams_menu,
            5: _settings_menu,
            6: _logs_traffic_screen,
            7: _geoblock_menu,
            8: _backup_menu,
            9: _telegram_menu,
            10: _update_screen,
        }.get(choice, lambda: None)()

        if choice == 0:
            break

    console.print("\n[dim]Goodbye.[/dim]\n")


# ── Logs screen ───────────────────────────────────────────────────────────────


def _logs_screen() -> None:
    _clear()
    console.print(_header_panel())
    console.print(Rule("[cyan]Proxy Logs (last 50 lines)[/cyan]"))
    try:
        from mtproxymaxpy.constants import INSTALL_DIR

        log_file = INSTALL_DIR / "telemt.log"
        if log_file.exists():
            for line in _read_last_lines(log_file, 50):
                console.print(f"  {line}")
        else:
            console.print("  [dim]Log file not found.[/dim]")
    except (OSError, ValueError) as exc:
        console.print(f"[red]Error: {exc}[/red]")
    _pause()


# ── Health check screen ───────────────────────────────────────────────────────


def _health_screen() -> None:
    _clear()
    console.print(_header_panel())
    console.print(Rule("[cyan]Health Check[/cyan]"))
    try:
        from mtproxymaxpy import doctor

        results = doctor.run_full_doctor()
        tbl = Table(show_header=True, box=None, padding=(0, 2))
        tbl.add_column("Check", style="bold", width=26)
        tbl.add_column("Status", width=8)
        tbl.add_column("Details")
        for r in results:
            ok = r.get("ok")
            if ok is True:
                status = "[green]PASS[/green]"
            elif ok is False:
                status = "[red]FAIL[/red]"
            else:
                status = "[dim]SKIP[/dim]"
            extra = {k: v for k, v in r.items() if k not in ("name", "ok")}
            details = "  ".join(f"{k}={v}" for k, v in extra.items()) if extra else ""
            tbl.add_row(r["name"], status, details)
        console.print(tbl)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        console.print(f"[red]Error: {exc}[/red]")
    _pause()


# ── Proxy Management menu ─────────────────────────────────────────────────────


def _proxy_menu() -> None:
    while True:
        _clear()
        console.print(_header_panel())
        console.print()

        running = False
        try:
            from mtproxymaxpy import process_manager as _pm

            running = _pm.is_running()
        except (OSError, RuntimeError):
            logger.debug("Failed to check proxy running state", exc_info=True)

        if running:
            console.print(_choice(1, "[red]Stop proxy[/red]"))
            console.print(_choice(2, "Restart proxy"))
        else:
            console.print(_choice(1, "[green]Start proxy[/green]"))
            console.print(_choice(2, "[dim]Restart proxy[/dim] (not running)"))

        console.print(
            _choice(3, "View logs"),
            _choice(4, "Health check"),
            _choice(5, "Status & Monitoring"),
            _choice(0, "Back"),
            sep="\n",
        )
        choice = _ask_choice(5)

        if choice == 0:
            return

        if choice in (1, 2):
            try:
                from mtproxymaxpy import process_manager as _pm2
                from mtproxymaxpy.utils.network import get_public_ip as _gip

                ip = _gip() or ""
                if running:
                    if choice == 1:
                        _pm2.stop()
                        console.print("[green][+] Proxy stopped.[/green]")
                    else:
                        pid = _pm2.restart(public_ip=ip)
                        console.print(f"[green][+] Proxy restarted (PID {pid})[/green]")
                elif choice == 1:
                    pid = _pm2.start(public_ip=ip)
                    console.print(f"[green][+] Proxy started (PID {pid})[/green]")
                else:
                    console.print("[yellow][!] Proxy is not running.[/yellow]")
            except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                console.print(f"[red][!] {exc}[/red]")
            _pause()

        elif choice == 3:
            _logs_screen()

        elif choice == 4:
            _health_screen()

        elif choice == 5:
            _status_screen()


# ── Status screen ──────────────────────────────────────────────────────────────


def _status_screen() -> None:
    _clear()
    console.print(_header_panel())
    try:
        from mtproxymaxpy import metrics as _metrics
        from mtproxymaxpy import process_manager
        from mtproxymaxpy.config.secrets import load_secrets
        from mtproxymaxpy.config.settings import load_settings
        from mtproxymaxpy.utils.formatting import format_bytes, format_duration
        from mtproxymaxpy.utils.network import get_public_ip
        from mtproxymaxpy.utils.proxy_link import build_proxy_links

        st = process_manager.status()
        settings = load_settings()
        secs = load_secrets()
        ip = settings.custom_ip or get_public_ip() or "?"

        tbl = Table(show_header=False, box=None, padding=(0, 2))
        tbl.add_column("Key", style="dim", width=22)
        tbl.add_column("Value")
        tbl.add_row("Status", "[green]Running[/green]" if st["running"] else "[red]Stopped[/red]")
        tbl.add_row("PID", str(st["pid"] or "—"))
        tbl.add_row("Port", str(settings.proxy_port))
        tbl.add_row("Domain (FakeTLS)", settings.proxy_domain)
        tbl.add_row("Public IP", ip)
        tbl.add_row("Concurrency", str(settings.proxy_concurrency))
        if st.get("uptime_sec") is not None:
            tbl.add_row("Uptime", format_duration(st["uptime_sec"]))
        tbl.add_row("Active secrets", str(sum(1 for s in secs if s.enabled)))

        console.print(Rule("[cyan]Proxy Status[/cyan]"))
        console.print(tbl)

        # Metrics
        mst = _metrics.get_stats()
        if mst.get("available"):
            console.print(Rule("[cyan]Traffic[/cyan]"))
            mtbl = Table(show_header=False, box=None, padding=(0, 2))
            mtbl.add_column("Key", style="dim", width=22)
            mtbl.add_column("Value")
            mtbl.add_row("Bytes in", format_bytes(mst["bytes_in"]))
            mtbl.add_row("Bytes out", format_bytes(mst["bytes_out"]))
            mtbl.add_row("Active connections", str(mst["active_connections"]))
            mtbl.add_row("Total connections", str(mst["total_connections"]))
            console.print(mtbl)

        # Proxy links for first enabled secret
        enabled = [s for s in secs if s.enabled]
        if enabled and ip != "?":
            s = enabled[0]
            tg_link, web_link = build_proxy_links(s.key, settings.proxy_domain, ip, settings.proxy_port)
            console.print(Rule("[cyan]Proxy Link[/cyan]"))
            console.print(f"  [dim]tg://[/dim]   {tg_link}")
            console.print(f"  [dim]https[/dim]   {web_link}")

    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        console.print(f"[red]Error: {exc}[/red]")

    _pause()


# ── Secrets menu ───────────────────────────────────────────────────────────────


def _secrets_menu() -> None:
    while True:
        _clear()
        console.print(_header_panel())
        try:
            from mtproxymaxpy.config.secrets import load_secrets

            secs = load_secrets()
        except (OSError, ValueError, RuntimeError):
            secs = []

        tbl = Table(show_header=True, box=None, padding=(0, 1))
        tbl.add_column("#", style="dim", width=4)
        tbl.add_column("Label", style="bold", width=22)
        tbl.add_column("Key (prefix)", width=12)
        tbl.add_column("En", width=3)
        tbl.add_column("Expires", width=12)
        tbl.add_column("Conns", width=6)
        tbl.add_column("Notes", width=20)
        for idx, s in enumerate(secs, 1):
            flag = "[green]✓[/green]" if s.enabled else "[red]✗[/red]"
            exp = s.expires or "never"
            conns = str(s.max_conns) if s.max_conns else "∞"
            tbl.add_row(str(idx), s.label, s.key[:10] + "…", flag, exp, conns, s.notes)

        console.print(Rule("[cyan]Secrets Management[/cyan]"))
        console.print(tbl)
        console.print()
        console.print(
            _choice(1, "Add secret"),
            _choice(2, "Remove secret"),
            _choice(3, "Rotate secret"),
            _choice(4, "Enable / Disable"),
            _choice(5, "Set limits"),
            _choice(6, "Extend expiry"),
            _choice(7, "Rename / Clone"),
            _choice(8, "Note"),
            _choice(9, "Show link & QR"),
            _choice(10, "Export CSV"),
            _choice(11, "Disable expired"),
            _choice(0, "Back"),
            sep="\n",
        )
        ch = _ask_choice(11)
        if ch == 0:
            return
        try:
            _secrets_action(ch, secs)
        except (KeyboardInterrupt, EOFError):
            return
        except (ValueError, KeyError, OSError, RuntimeError) as exc:
            console.print(f"[red]Error:[/red] {exc}")
            _pause()


def _secrets_action(ch: int, secs: list[Secret]) -> None:

    if ch == 1:
        _secret_add()
    elif ch == 2:
        label = Prompt.ask("  Label to remove", console=console)
        from mtproxymaxpy.config.secrets import remove_secret

        if remove_secret(label):
            console.print(f"[green][+] Removed '{label}'[/green]")
        else:
            console.print(f"[red][!] Not found: '{label}'[/red]")
        _pause()
    elif ch == 3:
        label = Prompt.ask("  Label to rotate", console=console)
        from mtproxymaxpy.config.secrets import rotate_secret

        s = rotate_secret(label)
        console.print(f"[green][+] New key: {s.key}[/green]")
        _pause()
    elif ch == 4:
        label = Prompt.ask("  Label", console=console)
        action = Prompt.ask("  Action", choices=["enable", "disable"], default="enable", console=console)
        from mtproxymaxpy.config.secrets import disable_secret, enable_secret

        fn = enable_secret if action == "enable" else disable_secret
        fn(label)
        console.print(f"[green][+] {action.capitalize()}d '{label}'[/green]")
        _pause()
    elif ch == 5:
        label = Prompt.ask("  Label", console=console)
        mc = IntPrompt.ask("  Max connections (0=unlimited)", default=0, console=console)
        mi = IntPrompt.ask("  Max unique IPs (0=unlimited)", default=0, console=console)
        qb_str = Prompt.ask("  Quota (e.g. 5G, 0=unlimited)", default="0", console=console)
        from mtproxymaxpy.config.secrets import set_secret_limits
        from mtproxymaxpy.utils.validation import parse_human_bytes

        qb = parse_human_bytes(qb_str) if qb_str != "0" else 0
        exp = Prompt.ask("  Expires (YYYY-MM-DD or blank)", default="", console=console)
        set_secret_limits(label, max_conns=mc, max_ips=mi, quota_bytes=qb, expires=exp or None)
        console.print("[green][+] Limits updated[/green]")
        _pause()
    elif ch == 6:
        label = Prompt.ask("  Label", console=console)
        days = IntPrompt.ask("  Extend by days", default=30, console=console)
        from mtproxymaxpy.config.secrets import extend_secret

        s = extend_secret(label, days)
        console.print(f"[green][+] New expiry: {s.expires}[/green]")
        _pause()
    elif ch == 7:
        action = Prompt.ask("  Action", choices=["rename", "clone"], default="rename", console=console)
        old = Prompt.ask("  Source label", console=console)
        new = Prompt.ask("  New label", console=console)
        if action == "rename":
            from mtproxymaxpy.config.secrets import rename_secret

            rename_secret(old, new)
        else:
            from mtproxymaxpy.config.secrets import clone_secret

            clone_secret(old, new)
        console.print("[green][+] Done[/green]")
        _pause()
    elif ch == 8:
        label = Prompt.ask("  Label", console=console)
        text = Prompt.ask("  Note text (blank to clear)", default="", console=console)
        from mtproxymaxpy.config.secrets import set_secret_note

        set_secret_note(label, text)
        console.print("[green][+] Note updated[/green]")
        _pause()
    elif ch == 9:
        _secret_show_link(secs)
    elif ch == 10:
        from mtproxymaxpy.config.secrets import export_secrets_csv

        csv_text = export_secrets_csv()
        console.print(csv_text)
        _pause()
    elif ch == 11:
        from mtproxymaxpy.config.secrets import disable_expired_secrets

        changed = disable_expired_secrets()
        console.print(f"[green][+] Disabled {len(changed)} expired secret(s)[/green]")
        _pause()


def _secret_add() -> None:
    from mtproxymaxpy.config.secrets import add_secret

    label = Prompt.ask("  Label", console=console)
    exp = Prompt.ask("  Expires (YYYY-MM-DD or blank)", default="", console=console)
    notes = Prompt.ask("  Notes (optional)", default="", console=console)
    s = add_secret(label, expires=exp, notes=notes)
    console.print(f"[green][+] Created '{s.label}': {s.key}[/green]")
    _pause()


def _secret_show_link(secs: list[Secret]) -> None:
    from mtproxymaxpy.config.settings import load_settings
    from mtproxymaxpy.utils.network import get_public_ip
    from mtproxymaxpy.utils.proxy_link import build_proxy_links, render_qr_terminal

    label = Prompt.ask("  Label (blank = first enabled)", default="", console=console)
    target = None
    target = next((s for s in secs if s.label == label), None) if label else next((s for s in secs if s.enabled), None)
    if target is None:
        console.print("[red][!] Secret not found[/red]")
        _pause()
        return

    settings = load_settings()
    ip = settings.custom_ip or get_public_ip() or "YOUR_SERVER_IP"
    tg_link, web_link = build_proxy_links(target.key, settings.proxy_domain, ip, settings.proxy_port)

    console.print()
    console.print(
        Panel(
            f"[bold]{target.label}[/bold]\n\n[dim]tg://[/dim]\n{tg_link}\n\n[dim]https[/dim]\n{web_link}",
            border_style="cyan",
        ),
    )
    qr = render_qr_terminal(web_link)
    if qr:
        console.print(qr)
    _pause()


def _links_menu() -> None:
    """Dedicated Share Links & QR screen, matching bash main-menu flow."""
    while True:
        _clear()
        console.print(_header_panel())
        console.print(Rule("[cyan]Share Links & QR[/cyan]"))

        try:
            from mtproxymaxpy.config.secrets import load_secrets

            secs = load_secrets()
        except (OSError, ValueError):
            secs = []

        enabled = [s for s in secs if s.enabled]
        console.print(f"  Enabled secrets: [bold]{len(enabled)}[/bold]")
        console.print()
        console.print(
            _choice(1, "Show all enabled links + QR"),
            _choice(2, "Show link + QR by label"),
            _choice(0, "Back"),
            sep="\n",
        )
        ch = _ask_choice(2)
        if ch == 0:
            return
        if ch == 2:
            _secret_show_link(secs)
            continue

        _clear()
        console.print(_header_panel())
        console.print(Rule("[cyan]Share Links & QR[/cyan]"))
        if not enabled:
            console.print("  [dim]No enabled secrets found.[/dim]")
            _pause()
            continue

        try:
            from mtproxymaxpy.config.settings import load_settings
            from mtproxymaxpy.utils.network import get_public_ip
            from mtproxymaxpy.utils.proxy_link import build_proxy_links, render_qr_terminal

            settings = load_settings()
            ip = settings.custom_ip or get_public_ip()
            if not ip:
                console.print("  [red][!] Cannot detect server IP[/red]")
                _pause()
                continue

            for s in enabled:
                tg_link, web_link = build_proxy_links(s.key, settings.proxy_domain, ip, settings.proxy_port)
                console.print()
                console.print(f"  [bold green]{s.label}[/bold green]")
                console.print("  [dim]" + "-" * 40 + "[/dim]")
                console.print(f"  [bold]TG Link:[/bold]  [cyan]{tg_link}[/cyan]")
                console.print(f"  [bold]Web Link:[/bold] [cyan]{web_link}[/cyan]")
                qr = render_qr_terminal(web_link)
                if qr:
                    console.print(qr)
        except (OSError, ValueError, RuntimeError) as exc:
            console.print(f"[red]Error:[/red] {exc}")
        _pause()


# ── Upstreams menu ─────────────────────────────────────────────────────────────


def _upstreams_menu() -> None:
    while True:
        _clear()
        console.print(_header_panel())
        from mtproxymaxpy.config.upstreams import load_upstreams

        ups = load_upstreams()

        tbl = Table(show_header=True, box=None, padding=(0, 1))
        tbl.add_column("#", style="dim", width=4)
        tbl.add_column("Name", style="bold", width=20)
        tbl.add_column("Type", width=8)
        tbl.add_column("Address", width=24)
        tbl.add_column("En", width=3)
        tbl.add_column("Wt", width=4)
        for idx, u in enumerate(ups, 1):
            flag = "[green]✓[/green]" if u.enabled else "[red]✗[/red]"
            tbl.add_row(str(idx), u.name, u.type, u.addr or "(direct)", flag, str(u.weight))

        console.print(Rule("[cyan]Upstream Proxies[/cyan]"))
        console.print(tbl)
        console.print()
        console.print(
            _choice(1, "Add upstream"),
            _choice(2, "Remove upstream"),
            _choice(3, "Enable / Disable"),
            _choice(4, "Test upstream"),
            _choice(0, "Back"),
            sep="\n",
        )
        ch = _ask_choice(4)
        if ch == 0:
            return
        try:
            _upstreams_action(ch, ups)
        except (ValueError, KeyError, OSError, RuntimeError) as exc:
            console.print(f"[red]Error:[/red] {exc}")
            _pause()


def _restart_proxy_if_running() -> None:
    from mtproxymaxpy import process_manager

    if process_manager.is_running():
        from mtproxymaxpy.utils.network import get_public_ip

        ip = get_public_ip() or ""
        pid = process_manager.restart(public_ip=ip)
        console.print(f"[green][+] Proxy restarted (PID {pid})[/green]")


def _upstreams_action(ch: int, ups: list[Upstream]) -> None:
    if ch == 1:
        from mtproxymaxpy.config.upstreams import add_upstream

        name = Prompt.ask("  Name", console=console)
        utype = Prompt.ask("  Type", choices=["socks5", "socks4", "direct"], default="socks5", console=console)
        addr = Prompt.ask("  Address (host:port)", default="", console=console)
        user = Prompt.ask("  Username (optional)", default="", console=console)
        pwd = Prompt.ask("  Password (optional)", default="", password=True, console=console)
        weight = IntPrompt.ask("  Weight (1-100)", default=10, console=console)
        add_upstream(name, type_=utype, addr=addr, user=user, password=pwd, weight=weight)
        console.print(f"[green][+] Added '{name}'[/green]")
        _restart_proxy_if_running()
        _pause()
    elif ch == 2:
        name = Prompt.ask("  Name to remove", console=console)
        from mtproxymaxpy.config.upstreams import remove_upstream

        remove_upstream(name)
        console.print(f"[green][+] Removed '{name}'[/green]")
        _restart_proxy_if_running()
        _pause()
    elif ch == 3:
        name = Prompt.ask("  Name to toggle", console=console)
        from mtproxymaxpy.config.upstreams import toggle_upstream

        updated = toggle_upstream(name)
        state = "enabled" if updated.enabled else "disabled"
        console.print(f"[green][+] Upstream '{name}' is now {state}[/green]")
        _restart_proxy_if_running()
        _pause()
    elif ch == 4:
        name = Prompt.ask("  Name to test", console=console)
        console.print("  Testing…")
        from mtproxymaxpy.config.upstreams import test_upstream

        result = test_upstream(name)
        if result.get("ok"):
            lat = result.get("latency_ms")
            console.print(f"[green][+] OK{f'  ({lat} ms)' if lat else ''}[/green]")
        else:
            console.print(f"[red][!] FAIL: {result.get('error')}[/red]")
        _pause()


# ── Settings menu ──────────────────────────────────────────────────────────────


def _settings_menu() -> None:
    while True:
        _clear()
        console.print(_header_panel())
        from mtproxymaxpy.config.settings import load_settings, save_settings

        settings = load_settings()

        tbl = Table(show_header=True, box=None, padding=(0, 2))
        tbl.add_column("#", style="bold cyan", width=3, justify="right")
        tbl.add_column("Setting", style="dim", width=34)
        tbl.add_column("Value")

        def _yes_no(*, value: bool) -> str:
            return "yes" if value else "no"

        menu_fields = [
            (1, "proxy_port", "Proxy port", str(settings.proxy_port), int),
            (2, "proxy_domain", "Proxy domain", settings.proxy_domain, str),
            (3, "proxy_concurrency", "Proxy concurrency", str(settings.proxy_concurrency), int),
            (4, "custom_ip", "Public IP override", settings.custom_ip or "(auto)", str),
            (5, "ad_tag", "Ad tag", settings.ad_tag or "(none)", str),
            (
                6,
                "masking_enabled",
                "Masking enabled",
                _yes_no(value=settings.masking_enabled),
                lambda v: v.lower() in ("true", "1", "yes", "on"),
            ),
            (7, "masking_host", "Masking host", settings.masking_host or "(none)", str),
            (8, "unknown_sni_action", "Unknown SNI action", settings.unknown_sni_action, str),
            (
                9,
                "proxy_protocol",
                "Proxy protocol enabled",
                _yes_no(value=settings.proxy_protocol),
                lambda v: v.lower() in ("true", "1", "yes", "on"),
            ),
            (
                10,
                "proxy_protocol_trusted_cidrs",
                "Trusted CIDRs (proxy protocol)",
                settings.proxy_protocol_trusted_cidrs or "(none)",
                str,
            ),
            (11, "proxy_cpus", "CPU limit", settings.proxy_cpus or "(unlimited)", str),
            (12, "proxy_memory", "Memory limit", settings.proxy_memory or "(unlimited)", str),
            (
                13,
                "auto_update_enabled",
                "Auto update enabled",
                _yes_no(value=settings.auto_update_enabled),
                lambda v: v.lower() in ("true", "1", "yes", "on"),
            ),
            (14, "geoblock_mode", "Geoblock mode", settings.geoblock_mode, str),
            (
                15,
                "telegram_enabled",
                "Telegram reports enabled",
                _yes_no(value=settings.telegram_enabled),
                lambda v: v.lower() in ("true", "1", "yes", "on"),
            ),
            (
                16,
                "telegram_bot_token",
                "Telegram bot token",
                ("*" * 8 + settings.telegram_bot_token[-4:]) if len(settings.telegram_bot_token) > 4 else settings.telegram_bot_token or "(not set)",
                str,
            ),
            (17, "telegram_chat_id", "Telegram chat ID", settings.telegram_chat_id or "(not set)", str),
            (18, "telegram_interval", "Telegram interval (h)", str(settings.telegram_interval), int),
            (19, "telegram_server_label", "Telegram server label", settings.telegram_server_label, str),
            (
                20,
                "manager_update_branch",
                "Manager update branch",
                getattr(settings, "manager_update_branch", "main"),
                lambda v: v.strip(),
            ),
        ]
        for n, _field, label, value, _converter in menu_fields:
            tbl.add_row(str(n), label, value)

        console.print(Rule("[cyan]Configuration[/cyan]"))
        console.print(tbl)
        console.print()
        console.print("  [dim]Tips:[/dim]")
        console.print("  [dim]- true/false: true, false, yes, no, 1, 0[/dim]")
        console.print("  [dim]- Unknown SNI action: mask | drop[/dim]")
        console.print("  [dim]- Trusted CIDRs: comma-separated, e.g. 10.0.0.0/8,192.168.0.0/16[/dim]")
        console.print("  [dim]- Leave empty to reset optional fields (where allowed)[/dim]")
        console.print()
        console.print("  Enter field number to edit, [bold cyan]0[/bold cyan] to go back")

        ch = _ask_choice(20)
        if ch == 0:
            return

        field_map = {n: (field, label, converter) for n, field, label, _value, converter in menu_fields}
        if ch in field_map:
            field, label, converter = field_map[ch]
            current = getattr(settings, field, "")
            new_val_str = Prompt.ask(f"  {label}", default=str(current), console=console)
            try:
                new_val = converter(new_val_str)  # type: ignore[operator]
                if field == "manager_update_branch":
                    if not new_val:
                        raise ValueError("manager_update_branch must not be empty")
                    if any(ch.isspace() for ch in new_val):
                        raise ValueError("manager_update_branch must not contain spaces")
                updated = settings.model_copy(update={field: new_val})
                save_settings(updated)
                console.print(f"[green][+] Saved {field} = {new_val}[/green]")
            except (ValueError, OSError) as exc:
                console.print(f"[red][!] {exc}[/red]")
            _pause()


# ── Metrics screen ─────────────────────────────────────────────────────────────


def _metrics_screen() -> None:
    _clear()
    console.print(_header_panel())
    console.print(Rule("[cyan]Traffic & Metrics[/cyan]"))
    try:
        from mtproxymaxpy import metrics as _metrics
        from mtproxymaxpy.utils.formatting import format_bytes

        stats = _metrics.get_stats()
        if not stats.get("available"):
            console.print(f"  [yellow][!] Metrics endpoint unavailable: {stats.get('error', 'unknown')}[/yellow]")
            console.print("  [dim]  Make sure the proxy is running and metrics_addr is reachable.[/dim]")
        else:
            tbl = Table(show_header=False, box=None, padding=(0, 2))
            tbl.add_column("Key", style="dim", width=24)
            tbl.add_column("Value")
            tbl.add_row("Bytes in (total)", format_bytes(stats["bytes_in"]))
            tbl.add_row("Bytes out (total)", format_bytes(stats["bytes_out"]))
            tbl.add_row("Active connections", str(stats["active_connections"]))
            tbl.add_row("Total connections", str(stats["total_connections"]))
            console.print(tbl)

            user_stats: dict[str, Any] = stats.get("user_stats", {})
            if user_stats:
                console.print()
                console.print(Rule("[cyan]Per-User Stats[/cyan]"))
                utbl = Table(show_header=True, box=None, padding=(0, 1))
                utbl.add_column("Key (prefix)", style="dim", width=14)
                utbl.add_column("Bytes in", width=12)
                utbl.add_column("Bytes out", width=12)
                utbl.add_column("Active", width=8)
                for key, us in user_stats.items():
                    utbl.add_row(
                        key[:12] + "…",
                        format_bytes(us.get("bytes_in", 0)),
                        format_bytes(us.get("bytes_out", 0)),
                        str(int(us.get("active", 0))),
                    )
                console.print(utbl)
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        console.print(f"[red]Error: {exc}[/red]")
    _pause()


def _stream_live_logs_screen() -> None:
    """Continuously refresh and show the latest proxy log lines until Ctrl+C."""
    try:
        from mtproxymaxpy.constants import INSTALL_DIR

        log_file = INSTALL_DIR / "telemt.log"
        if not log_file.exists():
            console.print("  [dim]Log file not found.[/dim]")
            _pause()
            return

        while True:
            _clear()
            console.print(_header_panel())
            console.print(Rule("[cyan]Live Proxy Logs[/cyan]"))
            console.print("  [dim][live - refreshing every 2s, Ctrl+C to stop][/dim]\n")
            for line in _read_last_lines(log_file, 30):
                console.print(f"  {line}")
            time.sleep(2)
    except KeyboardInterrupt:
        pass


def _stream_telegram_logs_screen() -> None:
    """Continuously refresh and show the latest Telegram bot log lines until Ctrl+C."""
    try:
        from mtproxymaxpy.constants import INSTALL_DIR

        log_file = INSTALL_DIR / "telegram-bot.log"
        if not log_file.exists():
            console.print("  [dim]Telegram bot log file not found.[/dim]")
            _pause()
            return

        while True:
            _clear()
            console.print(_header_panel())
            console.print(Rule("[cyan]Live Telegram Bot Logs[/cyan]"))
            console.print("  [dim][live - refreshing every 2s, Ctrl+C to stop][/dim]\n")
            for line in _read_last_lines(log_file, 30):
                console.print(f"  {line}")
            time.sleep(2)
    except KeyboardInterrupt:
        pass


def _connection_log_screen() -> None:
    """Show recent lines from connection.log."""
    _clear()
    console.print(_header_panel())
    console.print(Rule("[cyan]Connection Log[/cyan]"))
    try:
        from mtproxymaxpy.constants import CONNECTION_LOG

        if CONNECTION_LOG.exists() and CONNECTION_LOG.stat().st_size > 0:
            for line in _read_last_lines(CONNECTION_LOG, 50):
                console.print(f"  {line}")
        else:
            console.print("  [dim]Connection log is empty.[/dim]")
    except (OSError, ValueError) as exc:
        console.print(f"[red]Error: {exc}[/red]")
    _pause()


def _active_connections_screen() -> None:
    """Show active connection counters globally and per user."""
    _clear()
    console.print(_header_panel())
    console.print(Rule("[cyan]Active Connections[/cyan]"))
    try:
        from mtproxymaxpy import metrics as _metrics

        stats = _metrics.get_stats()
        if not stats.get("available"):
            console.print(f"  [yellow][!] Metrics endpoint unavailable: {stats.get('error', 'unknown')}[/yellow]")
            _pause()
            return

        console.print(f"  Global active connections: [bold]{stats['active_connections']}[/bold]\n")
        user_stats: dict[str, Any] = stats.get("user_stats", {})
        active_rows = [(key, int(us.get("active", 0))) for key, us in user_stats.items() if int(us.get("active", 0)) > 0]
        if not active_rows:
            console.print("  [dim]No active per-user connections right now.[/dim]")
        else:
            tbl = Table(show_header=True, box=None, padding=(0, 1))
            tbl.add_column("Key (prefix)", style="dim", width=14)
            tbl.add_column("Active", width=8)
            for key, active in active_rows:
                tbl.add_row(key[:12] + "…", str(active))
            console.print(tbl)
    except (OSError, ValueError, KeyError) as exc:
        console.print(f"[red]Error: {exc}[/red]")
    _pause()


def _metrics_live_screen() -> None:
    """Continuously refresh metrics screen until Ctrl+C."""
    try:
        while True:
            _clear()
            console.print(_header_panel())
            console.print(Rule("[cyan]Engine Metrics (live)[/cyan]"))
            from mtproxymaxpy import metrics as _metrics
            from mtproxymaxpy.utils.formatting import format_bytes

            stats = _metrics.get_stats()
            if not stats.get("available"):
                console.print(f"  [yellow][!] Metrics endpoint unavailable: {stats.get('error', 'unknown')}[/yellow]")
            else:
                tbl = Table(show_header=False, box=None, padding=(0, 2))
                tbl.add_column("Key", style="dim", width=24)
                tbl.add_column("Value")
                tbl.add_row("Bytes in (total)", format_bytes(stats["bytes_in"]))
                tbl.add_row("Bytes out (total)", format_bytes(stats["bytes_out"]))
                tbl.add_row("Active connections", str(stats["active_connections"]))
                tbl.add_row("Total connections", str(stats["total_connections"]))
                console.print(tbl)
            console.print("\n  [dim][live - refreshing every 5s, Ctrl+C to stop][/dim]")
            time.sleep(5)
    except KeyboardInterrupt:
        pass


def _logs_traffic_screen() -> None:
    """Bash-parity Logs & Traffic screen with summary and actions."""
    _clear()
    console.print(_header_panel())
    console.print(Rule("[cyan]Logs & Traffic[/cyan]"))

    try:
        from mtproxymaxpy import metrics as _metrics
        from mtproxymaxpy import process_manager
        from mtproxymaxpy.config.secrets import load_secrets
        from mtproxymaxpy.utils.formatting import format_bytes

        if not process_manager.is_running():
            console.print("\n  [dim]Proxy is not running[/dim]")
            _pause()
            return

        stats = _metrics.get_stats()
        if not stats.get("available"):
            console.print(f"  [yellow][!] Metrics endpoint unavailable: {stats.get('error', 'unknown')}[/yellow]")
            t_in = t_out = conns = 0
            user_stats = {}
        else:
            t_in = int(stats.get("bytes_in", 0))
            t_out = int(stats.get("bytes_out", 0))
            conns = int(stats.get("active_connections", 0))
            user_stats = stats.get("user_stats", {})

        console.print("\n  [bold]Total Traffic[/bold]")
        console.print(f"  Download: {format_bytes(t_in)}")
        console.print(f"  Upload:   {format_bytes(t_out)}")
        console.print(f"  Active Connections: {conns}")

        console.print("\n  [bold]Per-User Breakdown[/bold]")
        enabled = [s for s in load_secrets() if s.enabled]
        if not enabled:
            console.print("  [dim]No enabled users.[/dim]")
        else:
            for s in enabled:
                us = user_stats.get(s.label, {})
                u_in = int(us.get("bytes_in", 0))
                u_out = int(us.get("bytes_out", 0))
                u_active = int(us.get("active", 0))
                console.print(f"  [green]✓[/green] [bold]{s.label}[/bold]")
                console.print(f"    ↓ {format_bytes(u_in)}  ↑ {format_bytes(u_out)}  conns: {u_active}")

        console.print()
        console.print(
            _choice(1, "Stream live logs"),
            _choice(2, "Connection log"),
            _choice(3, "Engine metrics"),
            _choice(4, "Engine metrics (live)"),
            _choice(5, "Active connections"),
            _choice(0, "Back"),
            sep="\n",
        )
        choice = _ask_choice(5)
        if choice == 1:
            _stream_live_logs_screen()
        elif choice == 2:
            _connection_log_screen()
        elif choice == 3:
            _metrics_screen()
        elif choice == 4:
            _metrics_live_screen()
        elif choice == 5:
            _active_connections_screen()
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        console.print(f"[red]Error: {exc}[/red]")
        _pause()


# ── Geo-blocking menu ──────────────────────────────────────────────────────────


def _geoblock_menu() -> None:
    while True:
        _clear()
        console.print(_header_panel())
        from mtproxymaxpy import geoblock

        countries = geoblock.list_countries()

        console.print(Rule("[cyan]Security / Geo-blocking[/cyan]"))
        if countries:
            console.print(f"  Blocked countries: [bold red]{', '.join(countries)}[/bold red]")
        else:
            console.print("  No countries currently geo-blocked.")
        console.print()
        console.print(
            _choice(1, "Add country (by ISO code)"),
            _choice(2, "Remove country"),
            _choice(3, "Re-apply all rules"),
            _choice(4, "Clear all rules"),
            _choice(0, "Back"),
            sep="\n",
        )
        ch = _ask_choice(4)
        if ch == 0:
            return
        try:
            if ch == 1:
                cc = Prompt.ask("  Country code (e.g. RU, CN)", console=console).upper()
                console.print(f"  Downloading and applying rules for {cc}…")
                n = geoblock.add_country(cc)
                console.print(f"[green][+] Added {cc}: {n} CIDRs[/green]")
                _pause()
            elif ch == 2:
                cc = Prompt.ask("  Country code to remove", console=console).upper()
                geoblock.remove_country(cc)
                console.print(f"[green][+] Removed {cc}[/green]")
                _pause()
            elif ch == 3:
                console.print("  Re-applying all rules…")
                geoblock.reapply_all()
                console.print("[green][+] Done[/green]")
                _pause()
            elif ch == 4:
                if Confirm.ask("  Remove ALL geo-block rules?", console=console):
                    geoblock.clear_all()
                    console.print("[green][+] All rules cleared[/green]")
                    _pause()
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            console.print(f"[red]Error:[/red] {exc}")
            _pause()


# ── Backup menu ────────────────────────────────────────────────────────────────


def _backup_menu() -> None:
    while True:
        _clear()
        console.print(_header_panel())
        from mtproxymaxpy import backup
        from mtproxymaxpy.utils.formatting import format_bytes

        backups = backup.list_backups()
        console.print(Rule("[cyan]Backup & Restore[/cyan]"))
        if backups:
            tbl = Table(show_header=True, box=None, padding=(0, 1))
            tbl.add_column("#", style="dim", width=4)
            tbl.add_column("Filename", width=40)
            tbl.add_column("Size", width=10)
            tbl.add_column("Date", width=20)
            for i, b in enumerate(backups, 1):
                tbl.add_row(str(i), b["name"], format_bytes(b["size"]), b["mtime"].strftime("%Y-%m-%d %H:%M"))
            console.print(tbl)
        else:
            console.print("  No backups found.")
        console.print()
        console.print(
            _choice(1, "Create backup"),
            _choice(2, "Restore backup (by filename)"),
            _choice(0, "Back"),
            sep="\n",
        )
        ch = _ask_choice(2)
        if ch == 0:
            return
        try:
            if ch == 1:
                label = Prompt.ask("  Label (optional)", default="", console=console)
                path = backup.create_backup(label)
                console.print(f"[green][+] Backup created: {path.name}[/green]")
                _pause()
            elif ch == 2:
                name = Prompt.ask("  Filename (from list above)", console=console)
                from mtproxymaxpy.constants import BACKUP_DIR

                path = BACKUP_DIR / name
                if Confirm.ask(f"  Restore from '{name}'? (current config will be backed up)", console=console):
                    meta = backup.restore_backup(path)
                    console.print(f"[green][+] Restored. Original version: {meta.get('version', '?')}[/green]")
                    _pause()
        except (OSError, ValueError, RuntimeError) as exc:
            console.print(f"[red]Error:[/red] {exc}")
            _pause()


# ── Telegram menu ──────────────────────────────────────────────────────────────


def _telegram_menu() -> None:
    while True:
        _clear()
        console.print(_header_panel())
        from mtproxymaxpy.config.settings import load_settings, save_settings
        from mtproxymaxpy.constants import SYSTEMD_TELEGRAM_SERVICE, SYSTEMD_UNIT_DIR

        settings = load_settings()
        service_unit = SYSTEMD_UNIT_DIR / f"{SYSTEMD_TELEGRAM_SERVICE}.service"
        service_status = "[dim]unknown[/dim]"
        if not service_unit.exists():
            service_status = "[yellow]not installed[/yellow]"
        else:
            try:
                from mtproxymaxpy import systemd as _systemd

                service_status = "[green]running[/green]" if _systemd.is_active(SYSTEMD_TELEGRAM_SERVICE) else "[red]stopped[/red]"
            except (OSError, RuntimeError, subprocess.SubprocessError):
                service_status = "[dim]unknown[/dim]"

        console.print(Rule("[cyan]Telegram Bot[/cyan]"))
        tbl = Table(show_header=False, box=None, padding=(0, 2))
        tbl.add_column("Key", style="dim", width=26)
        tbl.add_column("Value")
        tbl.add_row("Configured enabled", "[green]yes[/green]" if settings.telegram_enabled else "[red]no[/red]")
        tbl.add_row("Service status", service_status)
        tbl.add_row(
            "Bot token",
            ("*" * 8 + settings.telegram_bot_token[-4:]) if len(settings.telegram_bot_token) > 4 else settings.telegram_bot_token or "(not set)",
        )
        tbl.add_row("Chat ID", settings.telegram_chat_id or "(not set)")
        tbl.add_row("Report interval (h)", str(settings.telegram_interval))
        tbl.add_row("Alerts enabled", str(settings.telegram_alerts_enabled))
        tbl.add_row("Server label", settings.telegram_server_label)
        console.print(tbl)
        console.print()
        console.print(
            _choice(1, "Setup wizard"),
            _choice(2, "Test (send message)"),
            _choice(3, "Enable / Disable"),
            _choice(4, "Set report interval"),
            _choice(5, "Toggle alerts"),
            _choice(6, "Install / Repair Telegram service"),
            _choice(7, "Stream telegram bot logs"),
            _choice(0, "Back"),
            sep="\n",
        )
        ch = _ask_choice(7)
        if ch == 0:
            return
        try:
            settings = load_settings()
            if ch == 1:
                _telegram_setup_wizard()
            elif ch == 2:
                _telegram_test()
            elif ch == 3:
                settings = settings.model_copy(update={"telegram_enabled": not settings.telegram_enabled})
                save_settings(settings)
                state = "enabled" if settings.telegram_enabled else "disabled"
                console.print(f"[green][+] Telegram bot {state}[/green]")

                try:
                    from mtproxymaxpy import systemd as _systemd

                    if settings.telegram_enabled:
                        if not service_unit.exists():
                            _systemd.install_telegram_service()
                            console.print("[green][+] Telegram service installed[/green]")
                        else:
                            _systemd.start_service(SYSTEMD_TELEGRAM_SERVICE)
                            console.print("[green][+] Telegram service started[/green]")
                    elif service_unit.exists():
                        _systemd.stop_service(SYSTEMD_TELEGRAM_SERVICE)
                        console.print("[yellow][*] Telegram service stopped[/yellow]")
                except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                    console.print(f"[yellow][!] Could not change service state: {exc}[/yellow]")
                _pause()
            elif ch == 4:
                hours = IntPrompt.ask("  Report interval (hours)", default=settings.telegram_interval, console=console)
                save_settings(settings.model_copy(update={"telegram_interval": hours}))
                console.print("[green][+] Saved[/green]")
                _pause()
            elif ch == 5:
                settings = settings.model_copy(update={"telegram_alerts_enabled": not settings.telegram_alerts_enabled})
                save_settings(settings)
                state = "enabled" if settings.telegram_alerts_enabled else "disabled"
                console.print(f"[green][+] Alerts {state}[/green]")
                _pause()
            elif ch == 6:
                from mtproxymaxpy import systemd as _systemd

                _systemd.install_telegram_service()
                console.print("[green][+] Telegram service installed and started[/green]")
                _pause()
            elif ch == 7:
                _stream_telegram_logs_screen()
        except (OSError, ValueError, RuntimeError) as exc:
            console.print(f"[red]Error:[/red] {exc}")
            _pause()


def _telegram_setup_wizard() -> None:
    from mtproxymaxpy.config.settings import load_settings, save_settings

    console.print()
    console.print(Rule("[cyan]Telegram Setup Wizard[/cyan]"))
    console.print("  1. Create a bot via @BotFather and copy the token.")
    console.print("  2. Start a chat with the bot, then send /start.")
    console.print("  3. Get your chat_id from @userinfobot or the Telegram API.")
    console.print()
    settings = load_settings()
    token = Prompt.ask("  Bot token", default=settings.telegram_bot_token, console=console)
    chat_id = Prompt.ask("  Chat ID", default=settings.telegram_chat_id, console=console)
    label = Prompt.ask("  Server label", default=settings.telegram_server_label, console=console)
    updated = settings.model_copy(
        update={
            "telegram_enabled": True,
            "telegram_bot_token": token,
            "telegram_chat_id": chat_id,
            "telegram_server_label": label,
        },
    )
    save_settings(updated)
    console.print("[green][+] Telegram bot configured and enabled[/green]")
    _pause()


def _telegram_test() -> None:
    import asyncio

    from aiogram import Bot

    from mtproxymaxpy.config.settings import load_settings

    settings = load_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        console.print("[red][!] Bot token or chat ID not configured[/red]")
        _pause()
        return
    try:

        async def _send_test() -> None:
            bot = Bot(token=settings.telegram_bot_token)
            try:
                await bot.send_message(settings.telegram_chat_id, "✅ MTProxyMaxPy test message — bot is working!")
            finally:
                await bot.session.close()

        asyncio.run(_send_test())
        console.print("[green][+] Test message sent[/green]")
    except (OSError, RuntimeError) as exc:
        console.print(f"[red][!] Failed: {exc}[/red]")
    _pause()


# ── Update screen ──────────────────────────────────────────────────────────────


def _update_screen() -> None:  # noqa: C901
    _clear()
    console.print(_header_panel())
    console.print(Rule("[cyan]Update[/cyan]"))

    # ── 1. Self-update (MTProxyMaxPy package) ─────────────────────────────
    console.print("\n  [bold]1. MTProxyMaxPy manager[/bold]")
    self_updated = False
    try:
        from mtproxymaxpy.constants import (
            INSTALL_DIR,
            UPDATE_BADGE_FILE,
            UPDATE_SHA_FILE,
        )

        branch = _manager_update_branch()
        commits_url = _manager_commits_url(branch)

        local_sha = ""
        try:
            r_local = subprocess.run(
                ["git", "-C", str(INSTALL_DIR), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            candidate = (r_local.stdout or "").strip().lower()
            if r_local.returncode == 0 and len(candidate) == 40 and all(c in "0123456789abcdef" for c in candidate):
                local_sha = candidate
        except (OSError, subprocess.SubprocessError):
            logger.debug("Failed to get local git SHA", exc_info=True)

        if not local_sha:
            local_sha = UPDATE_SHA_FILE.read_text().strip().lower() if UPDATE_SHA_FILE.exists() else ""

        console.print("  Checking GitHub for manager updates…")
        resp = httpx.get(
            commits_url,
            headers={"Accept": "application/vnd.github.sha"},
            timeout=15,
            follow_redirects=True,
        )
        remote_sha = resp.text.strip()[:40].lower()

        if local_sha and remote_sha == local_sha:
            console.print("  [green]✓ Already up to date[/green]")
            UPDATE_BADGE_FILE.unlink(missing_ok=True)
        else:
            console.print(f"  [yellow]⬆ New commits available on {branch}[/yellow]")
            if local_sha:
                console.print(f"  Local SHA  : [dim]{local_sha[:12]}…[/dim]")
            console.print(f"  Remote SHA : [dim]{remote_sha[:12]}…[/dim]")
            if Confirm.ask("  Update MTProxyMaxPy now?", console=console):
                import shutil as _shutil
                import subprocess as _sp
                from pathlib import Path as _Path

                git = _shutil.which("git")
                # uv is a system tool — check common locations
                uv = (
                    _shutil.which("uv")
                    or (_Path.home() / ".local" / "bin" / "uv" if (_Path.home() / ".local" / "bin" / "uv").exists() else None)
                    or (_Path("/usr/local/bin/uv") if _Path("/usr/local/bin/uv").exists() else None)
                )
                if not git:
                    console.print("[red][!] git not found in PATH[/red]")
                elif not uv:
                    console.print("[red][!] uv not found. Install from https://astral.sh/uv[/red]")
                else:
                    uv = str(uv)
                    console.print("  Pulling latest code…")
                    # Stash any local modifications (e.g. regenerated uv.lock)
                    # so that --ff-only pull is not blocked by a dirty tree.
                    _sp.run(
                        [git, "-C", str(INSTALL_DIR), "stash", "--quiet"],
                        capture_output=True,
                        text=True,
                    )
                    r_fetch = _sp.run(
                        [git, "-C", str(INSTALL_DIR), "fetch", "origin", branch],
                        capture_output=True,
                        text=True,
                    )
                    r0 = _sp.run(
                        [git, "-C", str(INSTALL_DIR), "checkout", branch],
                        capture_output=True,
                        text=True,
                    )
                    if r0.returncode != 0:
                        # Use FETCH_HEAD because origin/<branch> may be absent locally
                        # even when fetch succeeded (e.g. minimal/non-standard refspecs).
                        if r_fetch.returncode == 0:
                            r0 = _sp.run(
                                [git, "-C", str(INSTALL_DIR), "checkout", "-B", branch, "FETCH_HEAD"],
                                capture_output=True,
                                text=True,
                            )
                        else:
                            r0 = _sp.run(
                                [git, "-C", str(INSTALL_DIR), "checkout", "-b", branch, f"origin/{branch}"],
                                capture_output=True,
                                text=True,
                            )
                    if r0.returncode != 0:
                        out0 = "\n".join(
                            filter(
                                None,
                                [
                                    (r_fetch.stdout or "").strip(),
                                    (r_fetch.stderr or "").strip(),
                                    (r0.stdout or "").strip(),
                                    (r0.stderr or "").strip(),
                                ],
                            ),
                        )
                        if out0:
                            console.print(f"  {out0}")
                        console.print(f"[red][!] failed to switch to branch '{branch}'[/red]")
                        r1 = None
                    else:
                        r1 = _sp.run(
                            [git, "-C", str(INSTALL_DIR), "pull", "--ff-only", "origin", branch],
                            capture_output=True,
                            text=True,
                        )
                    # Always drop any stash created above — generated files
                    # (uv.lock etc.) will be recreated by uv sync anyway.
                    _sp.run(
                        [git, "-C", str(INSTALL_DIR), "stash", "drop", "--quiet"],
                        capture_output=True,
                        text=True,
                    )
                    if r1 is None:
                        pass
                    else:
                        out = "\n".join(filter(None, [r1.stdout.strip(), r1.stderr.strip()]))
                        if out:
                            console.print(f"  {out}")
                    if r1 is None or r1.returncode != 0:
                        console.print("[red][!] git pull failed[/red]")
                    else:
                        console.print("  Syncing dependencies…")
                        r2 = _sp.run(
                            [uv, "sync", "--no-dev"],
                            capture_output=True,
                            text=True,
                            cwd=str(INSTALL_DIR),
                        )
                        if r2.returncode == 0:
                            UPDATE_SHA_FILE.write_text(remote_sha)
                            UPDATE_BADGE_FILE.unlink(missing_ok=True)
                            console.print("[green][+] Manager updated successfully.[/green]")

                            # If Telegram bot runs as a dedicated systemd service,
                            # restart it so it picks up freshly updated code.
                            try:
                                from mtproxymaxpy import systemd as _svc
                                from mtproxymaxpy.constants import SYSTEMD_TELEGRAM_SERVICE

                                if _svc.is_active(SYSTEMD_TELEGRAM_SERVICE):
                                    _svc.restart_service(SYSTEMD_TELEGRAM_SERVICE)
                                    console.print("[green][+] Telegram bot service restarted.[/green]")
                            except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                                console.print(f"[yellow][!] Telegram bot service restart skipped: {exc}[/yellow]")

                            console.print("[bold yellow]  App will now close. Start 'mtproxymaxpy' again.[/bold yellow]")
                            self_updated = True
                        else:
                            console.print(f"[red][!] uv sync failed:\n{r2.stderr.strip()}[/red]")
    except (OSError, httpx.HTTPError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        console.print(f"  [red]Error checking manager update: {exc}[/red]")

    # ── 2. Engine update (telemt binary) ─────────────────────────────────
    console.print("\n  [bold]2. telemt engine[/bold]")
    try:
        from mtproxymaxpy import process_manager
        from mtproxymaxpy.constants import TELEMT_VERSION

        current = process_manager.get_binary_version() if hasattr(process_manager, "get_binary_version") else TELEMT_VERSION
        console.print(f"  Current: [bold]{current}[/bold]  Checking latest…")
        latest = process_manager.get_latest_version()
        console.print(f"  Latest:  [bold]{latest}[/bold]")

        if latest == current:
            console.print("  [green]✓ Engine up to date[/green]")
        else:
            console.print(f"  [yellow]⬆ Engine update: {current} → {latest}[/yellow]")
            if Confirm.ask("  Download and install engine update?", console=console):
                was_running = process_manager.is_running()
                if was_running:
                    process_manager.stop()
                console.print(f"  Downloading telemt {latest}…")
                process_manager.download_binary(version=latest, force=True)
                console.print("[green][+] Engine updated[/green]")
                if was_running:
                    from mtproxymaxpy.utils.network import get_public_ip

                    ip = get_public_ip() or ""
                    pid = process_manager.start(public_ip=ip)
                    console.print(f"[green][+] Proxy restarted (PID {pid})[/green]")
    except (OSError, httpx.HTTPError, RuntimeError, subprocess.SubprocessError) as exc:
        console.print(f"  [red]Error checking engine update: {exc}[/red]")

    if self_updated:
        raise SystemExit(0)
    _pause()


# ── First-run setup wizard ────────────────────────────────────────────────────

FAKETLS_DOMAINS = [
    "cloudflare.com",
    "www.google.com",
    "www.microsoft.com",
    "www.apple.com",
    "(custom)",
]


def _setup_wizard() -> None:  # noqa: C901
    """Interactive first-run configuration wizard."""
    _clear()
    console.print(
        Panel(
            "[bold cyan]Welcome to MTProxyMaxPy![/bold cyan]\n\nNo configuration found. Let's set up your proxy.",
            title="[bold]First-Run Setup[/bold]",
            border_style="cyan",
            padding=(1, 4),
        ),
    )
    console.print()

    # ── 1. Port ────────────────────────────────────────────────────────────────
    console.print(Rule("[cyan]1/6  Listen Port[/cyan]"))
    port = IntPrompt.ask(
        "  Proxy listen port",
        default=443,
        console=console,
    )

    # ── 2. Server IP ───────────────────────────────────────────────────────────
    console.print()
    console.print(Rule("[cyan]2/6  Server IP[/cyan]"))
    detected_ip = ""
    try:
        from mtproxymaxpy.utils.network import get_public_ip

        with console.status("  Detecting public IP…"):
            detected_ip = get_public_ip() or ""
    except (OSError, httpx.HTTPError, ValueError):
        logger.debug("Failed to detect public IP", exc_info=True)
    if detected_ip:
        console.print(f"  Detected: [green]{detected_ip}[/green]")
    raw_ip = Prompt.ask(
        "  Server IP or hostname",
        default=detected_ip or "",
        console=console,
    ).strip()
    custom_ip = raw_ip if raw_ip and raw_ip != detected_ip else ""

    # ── 3. FakeTLS domain ──────────────────────────────────────────────────────
    console.print()
    console.print(Rule("[cyan]3/6  FakeTLS Domain[/cyan]"))
    for i, d in enumerate(FAKETLS_DOMAINS, 1):
        console.print(f"    {i}) {d}")
    dom_choice = IntPrompt.ask(
        "  Choose domain",
        default=1,
        console=console,
    )
    if dom_choice == len(FAKETLS_DOMAINS):  # custom
        proxy_domain = Prompt.ask("  Enter custom domain", console=console).strip()
    else:
        proxy_domain = FAKETLS_DOMAINS[max(0, dom_choice - 1)]

    # ── 4. Traffic masking ─────────────────────────────────────────────────────
    console.print()
    console.print(Rule("[cyan]4/6  Traffic Masking[/cyan]"))
    console.print("  Forward DPI probes to the real FakeTLS site (recommended).")
    masking_enabled = Confirm.ask("  Enable traffic masking?", default=True, console=console)

    # ── 5. Ad-tag (optional) ───────────────────────────────────────────────────
    console.print()
    console.print(Rule("[cyan]5/6  Telegram Ad-tag (optional)[/cyan]"))
    console.print("  Earn revenue from Telegram sponsored channels.")
    ad_tag = ""
    if Confirm.ask("  Set an ad-tag?", default=False, console=console):
        ad_tag = Prompt.ask("  Ad-tag (32 hex chars)", console=console).strip()

    # ── 6. First secret ────────────────────────────────────────────────────────
    console.print()
    console.print(Rule("[cyan]6/6  First User Secret[/cyan]"))
    secret_label = (
        Prompt.ask(
            "  Label for first user",
            default="default",
            console=console,
        ).strip()
        or "default"
    )

    # ── Save settings ──────────────────────────────────────────────────────────
    console.print()
    console.print(Rule())
    console.print("  [bold]Saving configuration…[/bold]")
    try:
        from mtproxymaxpy.config.secrets import add_secret
        from mtproxymaxpy.config.settings import Settings, save_settings

        s = Settings(
            proxy_port=port,
            proxy_domain=proxy_domain,
            custom_ip=custom_ip,
            masking_enabled=masking_enabled,
            masking_host=proxy_domain if masking_enabled else "cloudflare.com",
            ad_tag=ad_tag,
        )
        save_settings(s)
        secret = add_secret(secret_label)
        console.print("  [green][+] Settings saved[/green]")
        console.print(f"  [green][+] Secret '{secret.label}' created: {secret.key}[/green]")
    except (OSError, ValueError, RuntimeError) as exc:
        console.print(f"  [red][!] Failed to save config: {exc}[/red]")
        _pause()
        return

    # ── Download binary ────────────────────────────────────────────────────────
    from mtproxymaxpy.constants import BINARY_PATH

    if not BINARY_PATH.exists():
        console.print("  [bold]Downloading telemt binary…[/bold]")
        try:
            from mtproxymaxpy import process_manager

            with console.status("  Downloading…"):
                process_manager.download_binary()
            console.print("  [green][+] Binary downloaded[/green]")
        except (OSError, httpx.HTTPError, RuntimeError) as exc:
            console.print(f"  [red][!] Download failed: {exc}[/red]")
            console.print("  [dim]Run 'mtproxymaxpy install' to retry.[/dim]")
            _pause()
            return

    # ── Start proxy ────────────────────────────────────────────────────────────
    console.print("  [bold]Starting proxy…[/bold]")
    try:
        from mtproxymaxpy import process_manager

        srv_ip = custom_ip or detected_ip or ""
        pid = process_manager.start(public_ip=srv_ip)
        console.print(f"  [green][+] Proxy started (PID {pid})[/green]")
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        console.print(f"  [red][!] Start failed: {exc}[/red]")

    # ── Install systemd ────────────────────────────────────────────────────────
    try:
        from mtproxymaxpy import systemd

        systemd.install()
        console.print("  [green][+] systemd service installed[/green]")
    except (OSError, RuntimeError, subprocess.SubprocessError):
        logger.debug("systemd install failed", exc_info=True)

    # ── Show proxy links ───────────────────────────────────────────────────────
    console.print()
    try:
        from mtproxymaxpy.utils.proxy_link import build_proxy_links

        srv_ip = custom_ip or detected_ip or "YOUR_IP"
        tg_link, web_link = build_proxy_links(secret.key, proxy_domain, srv_ip, port)
        console.print(
            Panel(
                f"[bold]Your proxy link:[/bold]\n\n[cyan]{tg_link}[/cyan]\n\n[dim]{web_link}[/dim]",
                title="[green]Installation Complete[/green]",
                border_style="green",
                padding=(1, 4),
            ),
        )
    except (OSError, ValueError, RuntimeError):
        console.print("  [green][+] Installation complete![/green]")

    # ── Telegram bot setup (optional) ─────────────────────────────────────────
    console.print()
    if Confirm.ask("  Set up Telegram bot for notifications?", default=False, console=console):
        _telegram_setup_wizard()

    _pause()


# ── Migration screen ───────────────────────────────────────────────────────────


def _migration_screen(legacy: dict[str, Any]) -> None:
    _clear()
    console.print(
        Panel(
            "[bold yellow]Legacy bash configuration detected![/bold yellow]\n\n"
            "MTProxyMaxPy can import your existing settings, secrets, upstreams and instances.\n"
            "Original files will NOT be modified.",
            title="[bold]Migration from MTProxyMax (bash)[/bold]",
            border_style="yellow",
        ),
    )
    files = "\n".join(f"  • {p}" for p in legacy.values() if p)
    console.print(f"\nDetected files:\n{files}\n")
    if Confirm.ask("  Import now?", default=True, console=console):
        try:
            from mtproxymaxpy.config.migration import run_migration

            result = run_migration(legacy)
            console.print(f"[green][+] Migration complete: {result}[/green]")
        except (OSError, ValueError, RuntimeError) as exc:
            console.print(f"[red][!] Migration failed: {exc}[/red]")
        _pause()
