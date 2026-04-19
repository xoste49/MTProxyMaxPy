"""systemd unit file generation and control for MTProxyMaxPy services."""

from __future__ import annotations

import logging
import subprocess
import sys

from mtproxymaxpy.constants import (
    INSTALL_DIR,
    SYSTEMD_SERVICE,
    SYSTEMD_TELEGRAM_SERVICE,
    SYSTEMD_UNIT_DIR,
)

logger = logging.getLogger(__name__)

# ── Unit file templates ────────────────────────────────────────────────────────


def _proxy_unit(python_exe: str) -> str:
    return f"""\
[Unit]
Description=MTProxyMaxPy — Telegram MTProto Proxy
After=network-online.target
Wants=network-online.target

[Service]
Type=forking
PIDFile={INSTALL_DIR}/telemt.pid
ExecStart={python_exe} -m mtproxymaxpy start --no-tui
ExecStop={python_exe} -m mtproxymaxpy stop --no-tui
ExecReload={python_exe} -m mtproxymaxpy restart --no-tui
Restart=on-failure
RestartSec=10
WorkingDirectory={INSTALL_DIR}
StandardOutput=append:{INSTALL_DIR}/telemt.log
StandardError=append:{INSTALL_DIR}/telemt.log

[Install]
WantedBy=multi-user.target
"""


def _telegram_unit(python_exe: str) -> str:
    return f"""\
[Unit]
Description=MTProxyMaxPy — Telegram Bot
After=network-online.target {SYSTEMD_SERVICE}.service
Wants=network-online.target

[Service]
Type=simple
ExecStart={python_exe} -m mtproxymaxpy telegram-bot --no-tui
Restart=on-failure
RestartSec=30
WorkingDirectory={INSTALL_DIR}
StandardOutput=append:{INSTALL_DIR}/telegram-bot.log
StandardError=append:{INSTALL_DIR}/telegram-bot.log

[Install]
WantedBy=multi-user.target
"""


# ── Install / uninstall ────────────────────────────────────────────────────────


def _python_exe() -> str:
    return sys.executable


def install(*, telegram: bool = False) -> None:
    """Write unit files and enable/start the proxy service."""
    if not SYSTEMD_UNIT_DIR.exists():
        raise RuntimeError("systemd unit directory not found — is this a systemd-based OS?")

    py = _python_exe()

    proxy_path = SYSTEMD_UNIT_DIR / f"{SYSTEMD_SERVICE}.service"
    proxy_path.write_text(_proxy_unit(py))

    if telegram:
        tg_path = SYSTEMD_UNIT_DIR / f"{SYSTEMD_TELEGRAM_SERVICE}.service"
        tg_path.write_text(_telegram_unit(py))

    _systemctl("daemon-reload")
    _systemctl("enable", SYSTEMD_SERVICE)
    try:
        _systemctl("start", SYSTEMD_SERVICE)
    except RuntimeError as exc:
        logger.warning("Could not start %s: %s", SYSTEMD_SERVICE, exc)

    if telegram:
        _systemctl("enable", SYSTEMD_TELEGRAM_SERVICE)
        try:
            _systemctl("start", SYSTEMD_TELEGRAM_SERVICE)
        except RuntimeError as exc:
            logger.warning("Could not start %s: %s", SYSTEMD_TELEGRAM_SERVICE, exc)


def install_telegram_service() -> None:
    """Write, enable, and start only the Telegram bot systemd unit."""
    if not SYSTEMD_UNIT_DIR.exists():
        raise RuntimeError("systemd unit directory not found — is this a systemd-based OS?")

    py = _python_exe()
    tg_path = SYSTEMD_UNIT_DIR / f"{SYSTEMD_TELEGRAM_SERVICE}.service"
    tg_path.write_text(_telegram_unit(py))

    _systemctl("daemon-reload")
    _systemctl("enable", SYSTEMD_TELEGRAM_SERVICE)
    try:
        _systemctl("start", SYSTEMD_TELEGRAM_SERVICE)
    except RuntimeError as exc:
        logger.warning("Could not start %s: %s", SYSTEMD_TELEGRAM_SERVICE, exc)


def uninstall(*, telegram: bool = True) -> None:
    """Stop and remove unit files."""
    for svc in [SYSTEMD_SERVICE] + ([SYSTEMD_TELEGRAM_SERVICE] if telegram else []):
        _systemctl("stop", svc, check=False)
        _systemctl("disable", svc, check=False)
        unit = SYSTEMD_UNIT_DIR / f"{svc}.service"
        unit.unlink(missing_ok=True)
    _systemctl("daemon-reload", check=False)


# ── Service control ────────────────────────────────────────────────────────────


def _systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(["systemctl"] + list(args), check=check, capture_output=True)
    except FileNotFoundError as exc:
        raise RuntimeError("systemctl not found — systemd is not available on this system") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"").decode(errors="replace").strip()
        raise RuntimeError(f"systemctl {' '.join(args)} failed (exit {exc.returncode}): {stderr}") from exc


def start_service(name: str = SYSTEMD_SERVICE) -> None:
    """Start the systemd service *name* via systemctl."""
    _systemctl("start", name)


def stop_service(name: str = SYSTEMD_SERVICE) -> None:
    """Stop the systemd service *name* via systemctl."""
    _systemctl("stop", name)


def restart_service(name: str = SYSTEMD_SERVICE) -> None:
    """Restart the systemd service *name* via systemctl."""
    _systemctl("restart", name)


def is_active(name: str = SYSTEMD_SERVICE) -> bool:
    """Return True if the systemd service *name* is currently active."""
    result = _systemctl("is-active", "--quiet", name, check=False)
    return result.returncode == 0


def is_enabled(name: str = SYSTEMD_SERVICE) -> bool:
    """Return True if the systemd service *name* is enabled (starts on boot)."""
    result = _systemctl("is-enabled", "--quiet", name, check=False)
    return result.returncode == 0
