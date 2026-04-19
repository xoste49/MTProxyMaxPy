"""Input validation utilities."""

import re
import socket


def validate_port(port: int | str) -> bool:
    """Return True if *port* is a valid TCP/UDP port number (1–65535)."""
    try:
        p = int(port)
    except (TypeError, ValueError):
        return False
    return 1 <= p <= 65535


def validate_domain(domain: str) -> bool:
    """Return True if *domain* looks like a valid hostname / FQDN."""
    if not domain or len(domain) > 253:
        return False
    # Each label: 1-63 chars, starts/ends with alnum, may contain hyphens
    label = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$")
    labels = domain.rstrip(".").split(".")
    return all(label.match(lbl) for lbl in labels)


def parse_human_bytes(value: str) -> int:
    """
    Parse a human-readable byte string like '5G', '500M', '2048' into bytes.

    Supported suffixes: B, K/KB, M/MB, G/GB, T/TB (case-insensitive).
    Raises ValueError for unrecognised input.
    """
    value = value.strip()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([BKMGT]B?)?", value, re.IGNORECASE)
    if not match:
        raise ValueError(f"Cannot parse byte value: {value!r}")
    number = float(match.group(1))
    suffix = (match.group(2) or "B").upper().rstrip("B") or "B"
    multipliers = {"B": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
    if suffix not in multipliers:
        raise ValueError(f"Unknown suffix in byte value: {value!r}")
    return int(number * multipliers[suffix])


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if the given port is not currently bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False
