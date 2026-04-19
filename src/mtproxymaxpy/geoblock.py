"""Geo-blocking via iptables + ipset.

Downloads country CIDR lists from ipdeny.com, creates an ipset hash:net per
country, and applies DROP rules in the iptables INPUT chain.  State is
persisted to geoblock.json so rules can be re-applied after a reboot.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any, cast

import httpx

from mtproxymaxpy.constants import INSTALL_DIR

logger = logging.getLogger(__name__)

GEO_CACHE_DIR = INSTALL_DIR / "geo"
GEO_CACHE_TTL = 86400  # 24 h
IPSET_PREFIX = "mtproxymaxpy"
IPDENY_URL = "https://www.ipdeny.com/ipblocks/data/aggregated/{cc}-aggregated.zone"
GEO_STATE_FILE = INSTALL_DIR / "geoblock.json"


# ── Internal helpers ───────────────────────────────────────────────────────────


def _run(*cmd: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(list(cmd), check=check, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Command not found: {cmd[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"{' '.join(cmd)} failed (exit {exc.returncode}): {exc.stderr.strip()}") from exc


def _require_tools() -> None:
    import shutil

    for tool in ("ipset", "iptables"):
        if not shutil.which(tool):
            raise RuntimeError(f"{tool} not found — install iptables and ipset first")


def _ipset_name(cc: str) -> str:
    return f"{IPSET_PREFIX}-{cc.lower()}"


def _download_cidrs(cc: str) -> list[str]:
    """Download (and cache for 24 h) CIDRs for a country code."""
    GEO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = GEO_CACHE_DIR / f"{cc.lower()}.zone"

    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < GEO_CACHE_TTL:
            return [l for l in cache_file.read_text().splitlines() if l.strip()]

    url = IPDENY_URL.format(cc=cc.lower())
    logger.info("Downloading CIDRs for %s …", cc)
    try:
        resp = httpx.get(url, timeout=30)
        resp.raise_for_status()
        cidrs = [l.strip() for l in resp.text.splitlines() if l.strip()]
        cache_file.write_text("\n".join(cidrs))
        return cidrs
    except (httpx.HTTPError, OSError, ValueError, RuntimeError) as exc:
        raise RuntimeError(f"Failed to download CIDRs for {cc}: {exc}") from exc


def _load_state() -> dict[str, Any]:
    if GEO_STATE_FILE.exists():
        try:
            return json.loads(GEO_STATE_FILE.read_text())  # type: ignore[no-any-return]
        except (json.JSONDecodeError, OSError):
            logger.debug("Failed to load geo state file", exc_info=True)
    return {"countries": [], "mode": "blacklist"}


def _save_state(state: dict[str, Any]) -> None:
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(state, indent=2).encode()
    fd, tmp = tempfile.mkstemp(dir=INSTALL_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
        Path(tmp).chmod(0o600)
        Path(tmp).replace(GEO_STATE_FILE)
    except Exception:
        with contextlib.suppress(OSError):
            Path(tmp).unlink()
        raise


# ── Public API ─────────────────────────────────────────────────────────────────


def add_country(cc: str) -> int:
    """Add a country to the geo-block list and apply iptables rules.

    Returns the number of CIDRs loaded.
    """
    _require_tools()
    cc = cc.upper()
    cidrs = _download_cidrs(cc)
    setname = _ipset_name(cc)

    # Create or flush the ipset
    _run("ipset", "create", setname, "hash:net", "family", "inet", check=False)
    _run("ipset", "flush", setname)

    # Populate
    for cidr in cidrs:
        if cidr:
            _run("ipset", "add", setname, cidr, check=False)

    # Add iptables rule only if it doesn't already exist
    probe = subprocess.run(
        ["iptables", "-C", "INPUT", "-m", "set", "--match-set", setname, "src", "-j", "DROP"],
        capture_output=True,
    )
    if probe.returncode != 0:
        _run(
            "iptables",
            "-I",
            "INPUT",
            "-m",
            "set",
            "--match-set",
            setname,
            "src",
            "-j",
            "DROP",
        )

    state = _load_state()
    if cc not in state["countries"]:
        state["countries"].append(cc)
    _save_state(state)

    logger.info("Geo-block added for %s (%d CIDRs)", cc, len(cidrs))
    return len(cidrs)


def remove_country(cc: str) -> None:
    """Remove the geo-block for a country code."""
    _require_tools()
    cc = cc.upper()
    setname = _ipset_name(cc)

    _run(
        "iptables",
        "-D",
        "INPUT",
        "-m",
        "set",
        "--match-set",
        setname,
        "src",
        "-j",
        "DROP",
        check=False,
    )
    _run("ipset", "destroy", setname, check=False)

    state = _load_state()
    state["countries"] = [c for c in state["countries"] if c != cc]
    _save_state(state)

    logger.info("Geo-block removed for %s", cc)


def list_countries() -> list[str]:
    result = _load_state().get("countries", [])
    return cast("list[str]", result)


def clear_all() -> None:
    """Remove all geo-block rules and wipe state."""
    for cc in list(list_countries()):
        try:
            remove_country(cc)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            logger.warning("Failed to clear geoblock for %s: %s", cc, exc)


def reapply_all() -> None:
    """Re-apply all stored country rules (called after proxy start)."""
    for cc in list_countries():
        try:
            add_country(cc)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            logger.warning("Failed to reapply geoblock for %s: %s", cc, exc)
