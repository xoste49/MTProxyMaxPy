# MTProxyMaxPy — Project Guidelines

Python port of `mtproxymax.sh` (bash, ~9300 lines). Manages a telemt-based MTProto proxy via a rich TUI and Typer CLI.

## Architecture

```
src/mtproxymaxpy/
  constants.py            — all paths, URLs, version pins
  process_manager.py      — start/stop/restart telemt binary, generate config.toml
  cli.py                  — Typer CLI (22 commands)
  systemd.py              — systemd unit generation & service management
  tui/
    menu.py               — Rich numbered-menu TUI (primary user interface)
    app.py                — re-export run_tui
  config/
    settings.py           — Pydantic Settings model, TOML persistence
    secrets.py            — Secret model, JSON persistence
    upstreams.py          — Upstream model, JSON persistence
    instances.py          — multi-port instances, Pydantic model + JSON persistence
    migration.py          — detect and migrate legacy bash config
  doctor.py               — diagnostic checks
  metrics.py              — telemt metrics endpoint reader
  backup.py               — config backup/restore
  geoblock.py             — iptables geo-blocking
  telegram_bot_aiogram.py — Telegram bot, aiogram 3 (17 commands)
  telegram_messages.py    — bot message builders (entity-based, aiogram.utils.formatting)
  utils/
    formatting.py         — output formatting helpers
    network.py            — network utilities
    system.py             — system utilities
    proxy_link.py         — proxy link generation
    validation.py         — input validation (port, domain, human-readable bytes)
install.sh                — installer: git clone + uv sync; on update: no TUI
tests/                    — 176 tests across 25 test files
```

Install location: `/opt/mtproxymaxpy/`
Legacy bash dir: `/opt/mtproxymax/` (no `py` suffix)

## Tech Stack

- **Python 3.13**, managed with **uv**
- **Rich** for TUI (numbered menus, not Textual)
- **Typer** for CLI
- **Pydantic v2** for config models
- **httpx** for HTTP (not requests)
- **aiogram 3** for Telegram bot
- **tomllib** (stdlib) for reading TOML, **tomli-w** for writing
- **qrcode** for QR code generation

## telemt Config Format

`process_manager._build_toml_config()` generates `/opt/mtproxymaxpy/mtproxy/config.toml`. Match the bash original exactly:

```toml
[general]            # not top-level keys
[general.modes]
[general.links]      # show = ["label1", "label2"]
[server]             # port =, not listen_addr =
[timeouts]
[censorship]         # tls_domain =, mask =, mask_host =
[access]
[access.users]       # "label" = "hexkey"  (keyed by label, not hex key)
[access.user_max_tcp_conns]
[access.user_expirations]
[[upstreams]]        # not [[upstream]]
```

telemt takes config path as **positional argument**: `telemt /path/to/config.toml` — no `--config` flag.

## Key Conventions

- **All paths** go through `constants.py` — never hardcode `/opt/mtproxymaxpy/` elsewhere
- **uv** for all package/env operations — not pip directly. Find uv via `shutil.which("uv")` or `~/.local/bin/uv`, never in `.venv/bin/`
- **Self-update** = `git pull --ff-only` + `uv sync --no-dev` in `INSTALL_DIR` — not `pip install git+...`
- **Atomic writes**: use `tempfile.mkstemp` + `os.replace` for all config file saves
- **TUI structure** mirrors bash: `[1] Proxy Management` → submenu with start/stop/restart/logs/health/status; Status screen is view-only
- **Background update check**: `_check_update_bg()` fires a daemon thread comparing GitHub HEAD SHA with `UPDATE_SHA_FILE`

## Build & Test

```bash
uv sync --no-dev          # install deps
uv run pytest tests/      # run smoke tests (100 tests)
uv run mtproxymaxpy       # launch TUI
uv run mtproxymaxpy --help
```

## Reference

Bash original (for feature parity): `mtproxymax.sh` in repo root.
