"""System detection and dependency checks."""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def check_root() -> None:
    """Exit with an error message if the process is not running as root."""
    if os.geteuid() != 0:
        print("Error: MTProxyMaxPy must be run as root.", file=sys.stderr)
        sys.exit(1)


def detect_os() -> str:
    """Return a normalised OS family string.

    Possible values: 'debian', 'rhel', 'alpine', 'unknown'.
    """
    os_release = Path("/etc/os-release")
    if os_release.exists():
        text = os_release.read_text().lower()
        if any(k in text for k in ("ubuntu", "debian")):
            return "debian"
        if any(k in text for k in ("rhel", "centos", "fedora", "rocky", "alma")):
            return "rhel"
        if "alpine" in text:
            return "alpine"
    return "unknown"


def check_dependencies() -> list[str]:
    """Ensure curl, awk, openssl, and ss/netstat are available.

    Attempts to install missing tools via the detected package manager.
    Returns a list of tool names that could not be installed.
    """
    required = ["curl", "awk", "openssl"]
    netstat_tools = ["ss", "netstat"]

    missing = [cmd for cmd in required if not shutil.which(cmd)]
    has_netstat = any(shutil.which(t) for t in netstat_tools)
    if not has_netstat:
        missing.append("iproute2")  # provides 'ss'

    if not missing:
        return []

    os_family = detect_os()
    install_cmds: dict[str, list[str]] = {
        "debian": ["apt-get", "install", "-y", "--no-install-recommends"],
        "rhel": ["yum", "install", "-y"],
        "alpine": ["apk", "add", "--no-cache"],
    }
    cmd_prefix = install_cmds.get(os_family)
    if cmd_prefix is None:
        return missing

    try:
        subprocess.run(
            cmd_prefix + missing,
            check=True,
            capture_output=True,
        )
        # Re-check after install
        still_missing = [
            cmd for cmd in (required + ["ss"])
            if not shutil.which(cmd)
        ]
        return still_missing
    except subprocess.CalledProcessError:
        return missing


def get_arch() -> str:
    """Return the architecture string used in telemt binary filenames.

    Returns 'x86_64' or 'aarch64'; raises RuntimeError for unsupported arches.
    """
    import platform
    machine = platform.machine().lower()
    mapping = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "aarch64": "aarch64",
        "arm64": "aarch64",
    }
    if machine not in mapping:
        raise RuntimeError(f"Unsupported architecture: {machine}")
    return mapping[machine]
