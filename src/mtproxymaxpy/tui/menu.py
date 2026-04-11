"""Rich-based interactive terminal menu for MTProxyMaxPy.

Replaces the Textual GUI-style app with a numbered-menu TUI similar to the
original bash script: box-drawing headers, coloured status, numbered choices.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Callable, Optional

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from mtproxymaxpy.constants import APP_TITLE, VERSION

console = Console(highlight=False)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _clear() -> None:
    console.clear()


def _pause() -> None:
    Prompt.ask("\n  [dim]Press Enter to continue…[/dim]", default="", console=console)


def _header_panel() -> Panel:
    """Build the status header shown at the top of every screen."""
    try:
        from mtproxymaxpy import process_manager
        st = process_manager.status()
        from mtproxymaxpy.config.settings import load_settings
        settings = load_settings()

        if st["running"]:
            status_txt = Text("● RUNNING", style="bold green")
        else:
            status_txt = Text("○ STOPPED", style="bold red")

        parts: list[Text] = [
            status_txt,
            Text(f"  Port: {settings.proxy_port}", style="cyan"),
        ]
        if st.get("uptime_sec") is not None:
            from mtproxymaxpy.utils.formatting import format_duration
            parts.append(Text(f"  Uptime: {format_duration(st['uptime_sec'])}", style="yellow"))
        if st["pid"]:
            parts.append(Text(f"  PID: {st['pid']}", style="dim"))
    except Exception:
        status_txt = Text("○ UNKNOWN", style="dim")
        parts = [status_txt]

    combined = Text()
    for p in parts:
        combined.append_text(p)

    title = f"[bold cyan]{APP_TITLE} v{VERSION}[/bold cyan]  [dim]Telegram MTProto Proxy Manager[/dim]"
    return Panel(combined, title=title, border_style="cyan", padding=(0, 2))


def _choice(n: int, label: str, hint: str = "") -> str:
    hint_part = f"  [dim]{hint}[/dim]" if hint else ""
    return f"  [bold cyan]{n}[/bold cyan]  {label}{hint_part}"


def _ask_choice(max_n: int, allow_zero: bool = True) -> int:
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


# ── Main Menu ──────────────────────────────────────────────────────────────────

def run_tui() -> None:
    """Entry point: run the interactive menu (blocking)."""
    from mtproxymaxpy.constants import SETTINGS_FILE

    if not SETTINGS_FILE.exists():
        # Check for legacy bash config first
        migrated = False
        try:
            from mtproxymaxpy.config.migration import detect_legacy
            legacy = detect_legacy()
            if legacy:
                _migration_screen(legacy)
                migrated = True
        except Exception:
            pass
        # Fresh install — run setup wizard
        if not migrated:
            _setup_wizard()

    while True:
        _clear()
        console.print(_header_panel())
        console.print()

        try:
            from mtproxymaxpy.config.secrets import load_secrets
            from mtproxymaxpy.config.upstreams import load_upstreams
            from mtproxymaxpy.config.settings import load_settings
            from mtproxymaxpy import geoblock

            n_secrets = len(load_secrets())
            n_upstreams = len(load_upstreams())
            n_geo = len(geoblock.list_countries())
            settings = load_settings()
            tg_hint = "enabled" if settings.telegram_enabled else "disabled"
            cfg_hint = f"port {settings.proxy_port} · {settings.proxy_domain}"
        except Exception:
            n_secrets = n_upstreams = n_geo = 0
            tg_hint = cfg_hint = ""

        console.print(
            _choice(1, "Status & Monitoring"),
            _choice(2, "Secrets Management", f"{n_secrets} user(s)"),
            _choice(3, "Upstream Proxies", f"{n_upstreams} upstream(s)"),
            _choice(4, "Configuration", cfg_hint),
            _choice(5, "Traffic & Metrics"),
            _choice(6, "Security / Geo-blocking", f"{n_geo} country/ies"),
            _choice(7, "Backup & Restore"),
            _choice(8, "Telegram Bot", tg_hint),
            _choice(9, "Update"),
            _choice(0, "[red]Exit[/red]"),
            sep="\n",
        )
        choice = _ask_choice(9)
        {
            1: _status_screen,
            2: _secrets_menu,
            3: _upstreams_menu,
            4: _settings_menu,
            5: _metrics_screen,
            6: _geoblock_menu,
            7: _backup_menu,
            8: _telegram_menu,
            9: _update_screen,
        }.get(choice, lambda: None)()

        if choice == 0:
            break

    console.print("\n[dim]Goodbye.[/dim]\n")


# ── Status screen ──────────────────────────────────────────────────────────────

def _status_screen() -> None:
    _clear()
    console.print(_header_panel())
    try:
        from mtproxymaxpy import process_manager, metrics as _metrics
        from mtproxymaxpy.config.settings import load_settings
        from mtproxymaxpy.config.secrets import load_secrets
        from mtproxymaxpy.utils.network import get_public_ip
        from mtproxymaxpy.utils.formatting import format_bytes, format_duration
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

    except Exception as exc:
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
        except Exception:
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
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            _pause()


def _secrets_action(ch: int, secs) -> None:
    from mtproxymaxpy import config

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
        from mtproxymaxpy.config.secrets import enable_secret, disable_secret
        fn = enable_secret if action == "enable" else disable_secret
        fn(label)
        console.print(f"[green][+] {action.capitalize()}d '{label}'[/green]")
        _pause()
    elif ch == 5:
        label = Prompt.ask("  Label", console=console)
        mc = IntPrompt.ask("  Max connections (0=unlimited)", default=0, console=console)
        mi = IntPrompt.ask("  Max unique IPs (0=unlimited)", default=0, console=console)
        qb_str = Prompt.ask("  Quota (e.g. 5G, 0=unlimited)", default="0", console=console)
        from mtproxymaxpy.utils.validation import parse_human_bytes
        from mtproxymaxpy.config.secrets import set_secret_limits
        qb = parse_human_bytes(qb_str) if qb_str != "0" else 0
        exp = Prompt.ask("  Expires (YYYY-MM-DD or blank)", default="", console=console)
        set_secret_limits(label, max_conns=mc, max_ips=mi, quota_bytes=qb,
                          expires=exp if exp else None)
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
        console.print(f"[green][+] Done[/green]")
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


def _secret_show_link(secs) -> None:
    from mtproxymaxpy.config.settings import load_settings
    from mtproxymaxpy.utils.network import get_public_ip
    from mtproxymaxpy.utils.proxy_link import build_proxy_links, render_qr_terminal

    label = Prompt.ask("  Label (blank = first enabled)", default="", console=console)
    target = None
    if label:
        target = next((s for s in secs if s.label == label), None)
    else:
        target = next((s for s in secs if s.enabled), None)
    if target is None:
        console.print("[red][!] Secret not found[/red]")
        _pause()
        return

    settings = load_settings()
    ip = settings.custom_ip or get_public_ip() or "YOUR_SERVER_IP"
    tg_link, web_link = build_proxy_links(target.key, settings.proxy_domain, ip, settings.proxy_port)

    console.print()
    console.print(Panel(
        f"[bold]{target.label}[/bold]\n\n"
        f"[dim]tg://[/dim]\n{tg_link}\n\n"
        f"[dim]https[/dim]\n{web_link}",
        border_style="cyan",
    ))
    qr = render_qr_terminal(web_link)
    if qr:
        console.print(qr)
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
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            _pause()


def _upstreams_action(ch: int, ups) -> None:
    if ch == 1:
        from mtproxymaxpy.config.upstreams import Upstream, load_upstreams, save_upstreams
        name = Prompt.ask("  Name", console=console)
        utype = Prompt.ask("  Type", choices=["socks5", "socks4", "direct"], default="socks5", console=console)
        addr = Prompt.ask("  Address (host:port)", default="", console=console)
        user = Prompt.ask("  Username (optional)", default="", console=console)
        pwd = Prompt.ask("  Password (optional)", default="", password=True, console=console)
        weight = IntPrompt.ask("  Weight (1-100)", default=100, console=console)
        items = load_upstreams()
        items.append(Upstream(name=name, type=utype, addr=addr, user=user, password=pwd, weight=weight))  # type: ignore
        save_upstreams(items)
        console.print(f"[green][+] Added '{name}'[/green]")
        _pause()
    elif ch == 2:
        name = Prompt.ask("  Name to remove", console=console)
        from mtproxymaxpy.config.upstreams import load_upstreams, save_upstreams
        items = load_upstreams()
        new = [u for u in items if u.name != name]
        if len(new) == len(items):
            console.print(f"[red][!] Not found: '{name}'[/red]")
        else:
            save_upstreams(new)
            console.print(f"[green][+] Removed '{name}'[/green]")
        _pause()
    elif ch == 3:
        name = Prompt.ask("  Name", console=console)
        action = Prompt.ask("  Action", choices=["enable", "disable"], default="enable", console=console)
        from mtproxymaxpy.config.upstreams import enable_upstream, disable_upstream
        fn = enable_upstream if action == "enable" else disable_upstream
        fn(name)
        console.print(f"[green][+] {action.capitalize()}d '{name}'[/green]")
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

        tbl = Table(show_header=False, box=None, padding=(0, 2))
        tbl.add_column("Key", style="dim", width=30)
        tbl.add_column("Value")
        fields = [
            ("1  proxy_port", str(settings.proxy_port)),
            ("2  proxy_domain", settings.proxy_domain),
            ("3  proxy_concurrency", str(settings.proxy_concurrency)),
            ("4  custom_ip", settings.custom_ip or "(auto)"),
            ("5  ad_tag", settings.ad_tag or "(none)"),
            ("6  masking_enabled", str(settings.masking_enabled)),
            ("7  masking_host", settings.masking_host),
            ("8  unknown_sni_action", settings.unknown_sni_action),
            ("9  proxy_protocol", str(settings.proxy_protocol)),
            ("10 proxy_protocol_trusted_cidrs", settings.proxy_protocol_trusted_cidrs or "(none)"),
            ("11 proxy_cpus", settings.proxy_cpus or "(unlimited)"),
            ("12 proxy_memory", settings.proxy_memory or "(unlimited)"),
            ("13 auto_update_enabled", str(settings.auto_update_enabled)),
            ("14 geoblock_mode", settings.geoblock_mode),
            ("15 telegram_enabled", str(settings.telegram_enabled)),
            ("16 telegram_bot_token", ("*" * 8 + settings.telegram_bot_token[-4:]) if len(settings.telegram_bot_token) > 4 else settings.telegram_bot_token or "(not set)"),
            ("17 telegram_chat_id", settings.telegram_chat_id or "(not set)"),
            ("18 telegram_interval (h)", str(settings.telegram_interval)),
            ("19 telegram_server_label", settings.telegram_server_label),
        ]
        for k, v in fields:
            tbl.add_row(k, v)

        console.print(Rule("[cyan]Configuration[/cyan]"))
        console.print(tbl)
        console.print()
        console.print("  Enter field number to edit, [bold cyan]0[/bold cyan] to go back")

        ch = _ask_choice(19)
        if ch == 0:
            return

        field_map = {
            1: ("proxy_port", int),
            2: ("proxy_domain", str),
            3: ("proxy_concurrency", int),
            4: ("custom_ip", str),
            5: ("ad_tag", str),
            6: ("masking_enabled", lambda v: v.lower() in ("true", "1", "yes", "on")),
            7: ("masking_host", str),
            8: ("unknown_sni_action", str),
            9: ("proxy_protocol", lambda v: v.lower() in ("true", "1", "yes", "on")),
            10: ("proxy_protocol_trusted_cidrs", str),
            11: ("proxy_cpus", str),
            12: ("proxy_memory", str),
            13: ("auto_update_enabled", lambda v: v.lower() in ("true", "1", "yes", "on")),
            14: ("geoblock_mode", str),
            15: ("telegram_enabled", lambda v: v.lower() in ("true", "1", "yes", "on")),
            16: ("telegram_bot_token", str),
            17: ("telegram_chat_id", str),
            18: ("telegram_interval", int),
            19: ("telegram_server_label", str),
        }
        if ch in field_map:
            field, converter = field_map[ch]
            current = getattr(settings, field)
            new_val_str = Prompt.ask(f"  {field}", default=str(current), console=console)
            try:
                new_val = converter(new_val_str)
                updated = settings.model_copy(update={field: new_val})
                save_settings(updated)
                console.print(f"[green][+] Saved {field} = {new_val}[/green]")
            except Exception as exc:
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

            user_stats: dict = stats.get("user_stats", {})
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
    except Exception as exc:
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
        except Exception as exc:
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
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            _pause()


# ── Telegram menu ──────────────────────────────────────────────────────────────

def _telegram_menu() -> None:
    while True:
        _clear()
        console.print(_header_panel())
        from mtproxymaxpy.config.settings import load_settings, save_settings
        settings = load_settings()

        console.print(Rule("[cyan]Telegram Bot[/cyan]"))
        tbl = Table(show_header=False, box=None, padding=(0, 2))
        tbl.add_column("Key", style="dim", width=26)
        tbl.add_column("Value")
        tbl.add_row("Enabled", "[green]yes[/green]" if settings.telegram_enabled else "[red]no[/red]")
        tbl.add_row("Bot token", ("*" * 8 + settings.telegram_bot_token[-4:]) if len(settings.telegram_bot_token) > 4 else settings.telegram_bot_token or "(not set)")
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
            _choice(0, "Back"),
            sep="\n",
        )
        ch = _ask_choice(5)
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
        except Exception as exc:
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
    updated = settings.model_copy(update={
        "telegram_enabled": True,
        "telegram_bot_token": token,
        "telegram_chat_id": chat_id,
        "telegram_server_label": label,
    })
    save_settings(updated)
    console.print("[green][+] Telegram bot configured and enabled[/green]")
    _pause()


def _telegram_test() -> None:
    from mtproxymaxpy.config.settings import load_settings

    settings = load_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        console.print("[red][!] Bot token or chat ID not configured[/red]")
        _pause()
        return
    try:
        import telebot
        bot = telebot.TeleBot(settings.telegram_bot_token)
        bot.send_message(settings.telegram_chat_id, "✅ MTProxyMaxPy test message — bot is working!")
        console.print("[green][+] Test message sent[/green]")
    except Exception as exc:
        console.print(f"[red][!] Failed: {exc}[/red]")
    _pause()


# ── Update screen ──────────────────────────────────────────────────────────────

def _update_screen() -> None:
    _clear()
    console.print(_header_panel())
    console.print(Rule("[cyan]Update[/cyan]"))
    try:
        from mtproxymaxpy import process_manager
        from mtproxymaxpy.constants import TELEMT_VERSION

        console.print(f"  Current telemt version: [bold]{TELEMT_VERSION}[/bold]")
        console.print("  Checking latest release on GitHub…")
        latest = process_manager.get_latest_version()
        console.print(f"  Latest available:       [bold]{latest}[/bold]")

        if latest == TELEMT_VERSION:
            console.print("[green]  ✓ Already up to date[/green]")
            _pause()
            return

        console.print(f"\n  [yellow]Update available: {TELEMT_VERSION} → {latest}[/yellow]")
        if Confirm.ask("  Download and install update?", console=console):
            was_running = process_manager.is_running()
            if was_running:
                process_manager.stop()
            console.print(f"  Downloading telemt {latest}…")
            process_manager.download_binary(version=latest, force=True)
            console.print("[green][+] Binary updated[/green]")
            if was_running:
                from mtproxymaxpy.utils.network import get_public_ip
                ip = get_public_ip() or ""
                pid = process_manager.start(public_ip=ip)
                console.print(f"[green][+] Proxy restarted (PID {pid})[/green]")
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")
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
    console.print(Panel(
        "[bold cyan]Welcome to MTProxyMaxPy![/bold cyan]\n\n"
        "No configuration found. Let's set up your proxy.",
        title="[bold]First-Run Setup[/bold]",
        border_style="cyan",
        padding=(1, 4),
    ))
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
    except Exception:
        pass
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
    secret_label = Prompt.ask(
        "  Label for first user",
        default="default",
        console=console,
    ).strip() or "default"

    # ── Save settings ──────────────────────────────────────────────────────────
    console.print()
    console.print(Rule())
    console.print("  [bold]Saving configuration…[/bold]")
    try:
        from mtproxymaxpy.config.settings import Settings, save_settings
        from mtproxymaxpy.config.secrets import add_secret

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
        console.print(f"  [green][+] Settings saved[/green]")
        console.print(f"  [green][+] Secret '{secret.label}' created: {secret.key}[/green]")
    except Exception as exc:
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
        except Exception as exc:
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
    except Exception as exc:
        console.print(f"  [red][!] Start failed: {exc}[/red]")

    # ── Install systemd ────────────────────────────────────────────────────────
    try:
        from mtproxymaxpy import systemd
        systemd.install()
        console.print("  [green][+] systemd service installed[/green]")
    except Exception:
        pass

    # ── Show proxy links ───────────────────────────────────────────────────────
    console.print()
    try:
        from mtproxymaxpy.utils.proxy_link import build_proxy_links
        srv_ip = custom_ip or detected_ip or "YOUR_IP"
        tg_link, web_link = build_proxy_links(secret.key, proxy_domain, srv_ip, port)
        console.print(Panel(
            f"[bold]Your proxy link:[/bold]\n\n"
            f"[cyan]{tg_link}[/cyan]\n\n"
            f"[dim]{web_link}[/dim]",
            title="[green]Installation Complete[/green]",
            border_style="green",
            padding=(1, 4),
        ))
    except Exception:
        console.print("  [green][+] Installation complete![/green]")

    # ── Telegram bot setup (optional) ─────────────────────────────────────────
    console.print()
    if Confirm.ask("  Set up Telegram bot for notifications?", default=False, console=console):
        _telegram_setup_wizard()

    _pause()


# ── Migration screen ───────────────────────────────────────────────────────────

def _migration_screen(legacy: dict) -> None:
    _clear()
    console.print(Panel(
        "[bold yellow]Legacy bash configuration detected![/bold yellow]\n\n"
        "MTProxyMaxPy can import your existing settings, secrets, upstreams and instances.\n"
        "Original files will NOT be modified.",
        title="[bold]Migration from MTProxyMax (bash)[/bold]",
        border_style="yellow",
    ))
    files = "\n".join(f"  • {p}" for p in legacy.values() if p)
    console.print(f"\nDetected files:\n{files}\n")
    if Confirm.ask("  Import now?", default=True, console=console):
        try:
            from mtproxymaxpy.config.migration import run_migration
            result = run_migration(legacy)
            console.print(f"[green][+] Migration complete: {result}[/green]")
        except Exception as exc:
            console.print(f"[red][!] Migration failed: {exc}[/red]")
        _pause()
