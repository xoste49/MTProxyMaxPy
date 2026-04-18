"""Doctor — comprehensive system diagnostics.

Runs a series of checks against the local installation and returns structured
results so that both the CLI and TUI can display them.
"""

from __future__ import annotations

import logging
import shutil
import socket
import subprocess
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

# ── Individual checks ──────────────────────────────────────────────────────────


def check_binary() -> dict[str, Any]:
    from mtproxymaxpy.constants import BINARY_PATH

    present = BINARY_PATH.exists() and bool(BINARY_PATH.stat().st_mode & 0o111)
    version: str | None = None
    if present:
        try:
            res = subprocess.run(
                [str(BINARY_PATH), "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            version = (res.stdout + res.stderr).strip().split()[-1]
        except (OSError, subprocess.SubprocessError):
            logger.debug("Failed to get telemt version", exc_info=True)
    return {"ok": present, "version": version, "path": str(BINARY_PATH)}


def check_process() -> dict[str, Any]:
    from mtproxymaxpy import process_manager

    running = process_manager.is_running()
    return {"ok": running, "running": running, "pid": process_manager.get_pid()}


def check_port_listening(port: int) -> dict[str, Any]:
    """Check whether the proxy port is actively listening."""
    # Try ss (modern iproute2)
    if shutil.which("ss"):
        try:
            res = subprocess.run(
                ["ss", "-tlnp"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            listening = f":{port}" in res.stdout or f" {port} " in res.stdout
            return {"ok": listening, "tool": "ss"}
        except (OSError, subprocess.SubprocessError):
            logger.debug("ss port check failed", exc_info=True)
    # Fallback use netstat
    if shutil.which("netstat"):
        try:
            res = subprocess.run(
                ["netstat", "-tlnp"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            listening = f":{port}" in res.stdout
            return {"ok": listening, "tool": "netstat"}
        except (OSError, subprocess.SubprocessError):
            logger.debug("netstat port check failed", exc_info=True)
    # Last resort: try connecting
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return {"ok": True, "tool": "socket"}
    except OSError:
        return {"ok": False, "tool": "socket", "note": "port not reachable"}


def check_tls_handshake(host: str, port: int, domain: str = "") -> dict[str, Any]:
    """Attempt a TLS handshake via openssl s_client."""
    if not shutil.which("openssl"):
        return {"ok": None, "note": "openssl not available"}
    cmd = ["openssl", "s_client", "-connect", f"{host}:{port}", "-brief"]
    if domain:
        cmd += ["-servername", domain]
    try:
        proc = subprocess.run(
            cmd,
            input=b"",
            capture_output=True,
            timeout=10,
        )
        ok = proc.returncode == 0 or b"Protocol" in proc.stdout
        return {"ok": ok, "output": (proc.stdout + proc.stderr)[:200].decode(errors="replace")}
    except subprocess.TimeoutExpired:
        return {"ok": False, "note": "timeout"}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "note": str(exc)}


def check_secrets() -> dict[str, Any]:
    from mtproxymaxpy.config.secrets import load_secrets

    all_secrets = load_secrets()
    today = date.today().isoformat()
    expired = [s.label for s in all_secrets if s.expires and s.expires < today]
    enabled = [s for s in all_secrets if s.enabled]
    return {
        "ok": len(enabled) > 0,
        "total": len(all_secrets),
        "enabled": len(enabled),
        "expired": expired,
    }


def check_disk_space(min_mb: int = 500) -> dict[str, Any]:
    from mtproxymaxpy.constants import INSTALL_DIR

    path = str(INSTALL_DIR) if INSTALL_DIR.exists() else "/"
    stat = shutil.disk_usage(path)
    free_mb = stat.free // (1024 * 1024)
    return {"ok": free_mb >= min_mb, "free_mb": free_mb, "min_mb": min_mb}


def check_metrics_endpoint() -> dict[str, Any]:
    from mtproxymaxpy import metrics as _metrics

    stats = _metrics.get_stats()
    return {"ok": stats.get("available", False), "error": stats.get("error")}


def check_telegram_service() -> dict[str, Any]:
    from mtproxymaxpy.config.settings import load_settings
    from mtproxymaxpy.constants import SYSTEMD_TELEGRAM_SERVICE

    settings = load_settings()
    if not settings.telegram_enabled:
        return {"ok": True, "note": "disabled"}
    if shutil.which("systemctl"):
        from mtproxymaxpy import systemd

        active = systemd.is_active(SYSTEMD_TELEGRAM_SERVICE)
        return {"ok": active, "service": SYSTEMD_TELEGRAM_SERVICE}
    return {"ok": None, "note": "systemctl not available"}


# ── Full doctor run ────────────────────────────────────────────────────────────


def run_full_doctor() -> list[dict[str, Any]]:
    """Run all diagnostic checks.

    Returns a list of dicts: ``{name, ok, **extras}``.
    ``ok`` is True/False/None (True=pass, False=fail, None=skipped/N/A).
    """
    from mtproxymaxpy.config.settings import load_settings

    settings = load_settings()
    results: list[dict[str, Any]] = []

    def add(name: str, result: dict[str, Any]) -> None:
        results.append({"name": name, **result})

    add("Binary present", check_binary())
    add("Process running", check_process())
    add("Port listening", check_port_listening(settings.proxy_port))
    add(
        "TLS handshake",
        check_tls_handshake("127.0.0.1", settings.proxy_port, settings.proxy_domain),
    )
    add("Secrets configured", check_secrets())
    add("Disk space", check_disk_space())
    add("Metrics endpoint", check_metrics_endpoint())
    add("Telegram service", check_telegram_service())
    return results
