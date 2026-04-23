<p align="center">
  <h1 align="center">MTProxyMaxPy</h1>
  <p align="center"><b>The Ultimate Telegram MTProto Proxy Manager</b></p>
  <p align="center">
    Interactive TUI &middot; Full CLI &middot; Telegram Bot &middot; Per-user Access Control
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/version-1.0.0-brightgreen" alt="Version"/>
    <img src="https://img.shields.io/badge/license-MIT-blue" alt="License"/>
    <img src="https://img.shields.io/badge/engine-Rust_(telemt_3.x)-orange" alt="Engine"/>
    <img src="https://img.shields.io/badge/platform-Linux-lightgrey" alt="Platform"/>
    <img src="https://img.shields.io/badge/python-3.13+-yellow" alt="Python"/>
  </p>
  <p align="center">
    <a href="#-quick-start">Quick Start</a> &bull;
    <a href="#-features">Features</a> &bull;
    <a href="#-comparison">Comparison</a> &bull;
    <a href="#-telegram-bot">Telegram Bot</a> &bull;
    <a href="#-cli-reference">CLI Reference</a> &bull;
    <a href="#-changelog">Changelog</a>
  </p>
</p>

---

MTProxyMaxPy is a full-featured Telegram MTProto proxy manager powered by the **telemt 3.x Rust engine**. It wraps the raw proxy engine with an interactive TUI, a complete CLI, a Telegram bot for remote management, per-user access control, traffic monitoring, and proxy chaining — all as a clean Python application.

```bash
sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/xoste49/MTProxyMaxPy/main/install.sh)"
```

---

## Why MTProxyMaxPy?

Most MTProxy tools give you a proxy and a link. That is it. MTProxyMaxPy gives you a **full management platform**:

- **Multi-user secrets** with individual bandwidth quotas, device limits, and expiry dates
- **Telegram bot** — manage everything from your phone
- **Interactive TUI** — no need to memorize commands, menu-driven setup
- **Real-time traffic stats** — real per-user data from the engine
- **Proxy chaining** — route through SOCKS5 upstreams for extra privacy
- **Auto-recovery** — detects downtime, restarts automatically, alerts you on Telegram
- **Pure Python** — no Docker, no Bash, easy to extend

---

## Quick Start

### One-Line Install

```bash
sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/xoste49/MTProxyMaxPy/main/install.sh)"
```

The interactive wizard walks you through everything: port, domain, first user secret, and optional Telegram bot setup.

### Manual Install

```bash
curl -fsSL https://raw.githubusercontent.com/xoste49/MTProxyMaxPy/main/install.sh -o install.sh
sudo bash install.sh
```

### After Install

```bash
mtproxymaxpy           # Open interactive TUI
mtproxymaxpy status    # Check proxy health
```

---

## Features

### FakeTLS V2 Obfuscation

Proxy traffic is indistinguishable from normal HTTPS. The **telemt** engine mirrors real TLS 1.3 sessions — per-domain profiles, real cipher suites, dynamic certificate lengths, and realistic record fragmentation. The SNI points to a cover domain (e.g. `cloudflare.com`), so DPI sees ordinary web browsing.

**Traffic masking** — when a non-Telegram client probes the server, the connection is forwarded to the real cover domain and responds exactly as it would.

---

### Multi-User Secret Management

Each user gets their own **secret key** with a human-readable label:

- **Add/remove** users instantly — config regenerates and proxy hot-reloads
- **Enable/disable** access without deleting the key
- **Rotate** a user's secret — new key, same label, old link stops working
- **QR codes** — scannable directly in Telegram

---

### Per-User Access Control

Fine-grained limits enforced at the engine level:

| Limit | Description | Example |
|-------|-------------|---------|
| **Max Connections** | Concurrent TCP connections (~3 per device) | `15` |
| **Max IPs** | Unique IP addresses allowed | `5` |
| **Data Quota** | Lifetime bandwidth cap | `10G` |
| **Expiry Date** | Auto-disable after date | `2026-12-31` |

```bash
mtproxymaxpy secret add alice
mtproxymaxpy secret list
mtproxymaxpy secret rotate alice
mtproxymaxpy secret remove alice
```

---

### Telegram Bot

Full proxy management from your phone. Supports `/status`, `/users`, `/restart` and sends automatic alerts:

- Proxy down: instant notification + auto-restart attempt
- Proxy recovered: notification with connection details
- Periodic traffic reports at your chosen interval

```bash
mtproxymaxpy telegram-bot          # Run bot (used by systemd)
```

Configure via TUI (Settings screen) or edit `settings.toml` directly.

---

### Proxy Chaining (Upstream Routing)

Route traffic through intermediate servers:

```bash
mtproxymaxpy upstream add warp socks5 127.0.0.1:40000 --weight 20
mtproxymaxpy upstream add backup socks5 203.0.113.50:1080 --user user --password pass
mtproxymaxpy upstream list
mtproxymaxpy upstream remove warp
```

Supports **SOCKS5** (with auth), **SOCKS4**, and **direct** routing with weight-based load balancing.

---

### Real-Time Traffic Monitoring

```bash
mtproxymaxpy status    # Overview with connection count and uptime
```

Per-user traffic data is read directly from the telemt engine stats.

---

## Comparison

| Feature | **MTProxyMaxPy** | **mtg v2** (Go) | **Official MTProxy** (C) |
|---------|:-:|:-:|:-:|
| Engine | telemt 3.x (Rust) | mtg (Go) | MTProxy (C) |
| FakeTLS | Yes | Yes | No |
| Traffic Masking | Yes | Yes | No |
| Multi-User Secrets | Yes (unlimited) | No (1 secret) | Multi-secret |
| Per-User Limits | Yes (conns, IPs, quota, expiry) | No | No |
| Per-User Traffic Stats | Yes | No | No |
| Telegram Bot | Yes | No | No |
| Interactive TUI | Yes | No | No |
| Proxy Chaining | Yes (SOCKS5/4, weighted) | Yes (SOCKS5) | No |
| QR Code Generation | Yes | No | No |
| Auto-Recovery | Yes (with alerts) | No | No |
| Auto-Update | Yes | No | No |
| Active Development | Yes | Yes | Abandoned |

---

## Architecture

```
Telegram Client
      |
      v
+-------------------------+
|  Your Server (port 443) |
|  +-------------------+  |
|  |  telemt binary    |  |  <- Rust/Tokio engine (native)
|  |  (FakeTLS v2)     |  |
|  +------+------------+  |
|         |               |
|  +------+------+        |
|  v             v        |
|  Direct    SOCKS5       |  <- Upstream routing
+-------------------------+
          |
          v
   Telegram Servers
```

| Component | Role |
|-----------|------|
| **mtproxymaxpy** | Python CLI + TUI: config manager, process supervisor |
| **telemt** | Native Rust binary — MTProto engine |
| **Telegram bot service** | Independent systemd service (`mtproxymaxpy-telegram`) |
| **settings.toml** | Proxy configuration (Pydantic-validated TOML) |
| **secrets.json** | User secrets with per-user limits |

---

## CLI Reference

### Proxy Management

```bash
mtproxymaxpy install              # Download telemt binary and run setup wizard
mtproxymaxpy start                # Start proxy
mtproxymaxpy stop                 # Stop proxy
mtproxymaxpy restart              # Restart proxy
mtproxymaxpy status               # Show proxy status
mtproxymaxpy update               # Download latest telemt binary and restart
mtproxymaxpy version              # Print version
```

### User Secrets

```bash
mtproxymaxpy secret add <label>           # Add user
mtproxymaxpy secret remove <label>        # Remove user
mtproxymaxpy secret list                  # List all users
mtproxymaxpy secret rotate <label>        # New key, same label
```

### Upstream Routing

```bash
mtproxymaxpy upstream add <name> <type> <host:port> [--user U] [--password P] [--weight W]
mtproxymaxpy upstream list
mtproxymaxpy upstream remove <name>
```

### Telegram Bot

```bash
mtproxymaxpy telegram-bot         # Run bot process (blocking, for systemd)
```

Bot token and chat ID are configured via TUI (Settings screen) or directly in `settings.toml`.

---

## System Requirements

| Requirement | Details |
|-------------|---------|
| **OS** | Ubuntu, Debian, CentOS, RHEL, Fedora, Rocky, AlmaLinux |
| **Python** | 3.13+ |
| **uv** | Auto-installed by `install.sh` |
| **RAM** | 256 MB minimum |
| **Access** | Root required |

---

## Configuration Files

All files are stored under `/opt/mtproxymaxpy/` with mode `600`.

| File | Purpose |
|------|---------|
| `settings.toml` | Proxy settings (port, domain, Telegram bot, etc.) |
| `secrets.json` | User keys, limits, expiry dates |
| `upstreams.json` | Upstream routing rules |
| `instances.json` | Multi-port instance definitions |
| `mtproxy/config.toml` | Auto-generated telemt engine config |

---

## Development

### Run Tests In Debian (Docker)

To validate Linux-specific behavior (for example file permission checks), run tests in the dedicated Debian 13 test container:

```bash
make test
```

Equivalent direct command:

```bash
docker compose run --rm test
```

This command works the same on Linux/macOS/Windows and runs `pytest` with coverage inside Debian 13 (`debian:trixie-slim`).

### Pre-commit

This project uses `pre-commit` for lightweight checks and Ruff lint/format hooks.

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

### Ruff

Run lint checks:

```bash
uv run ruff check .
uv run ruff check . --fix
```

Run formatter:

```bash
uv run ruff format .
uv run ruff format --check .
```

---

## Changelog

### v1.0.0 — Python Rewrite

Complete rewrite from Bash to Python 3.13:

- Replaced Bash + Docker stack with a native Python application managed by uv
- **Textual TUI** — fully interactive menu-driven interface
- **Pydantic models** — all config validated at load time, stored as TOML + JSON
- **Native telemt binary** — no Docker required; binary downloaded from GitHub releases
- **aiogram** — Telegram bot backend with command parity
- **Typer CLI** — `install`, `start`, `stop`, `restart`, `status`, `update`, `secret`, `upstream`
- Removed: replication (master-slave sync), Docker, iptables geo-blocking

---

## Credits

Built on top of **[telemt](https://github.com/telemt/telemt)** — a high-performance MTProto proxy engine written in Rust/Tokio. All proxy protocol handling, FakeTLS, traffic masking, and per-user enforcement is powered by telemt.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

The **telemt engine** binary is licensed under the [Telemt Public License 3 (TPL-3)](https://github.com/telemt/telemt/blob/main/LICENSE).

Copyright (c) 2026 xoste49
