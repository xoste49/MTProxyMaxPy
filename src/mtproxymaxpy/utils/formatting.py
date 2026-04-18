"""Human-readable formatting helpers."""

import re


def format_bytes(n: int | float) -> str:
    """Return a human-readable byte size string."""
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            if unit == "B":
                return f"{int(n)} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def format_duration(seconds: int) -> str:
    """Format a duration in seconds as e.g. '2d 3h 45m'."""
    seconds = int(seconds)
    if seconds < 0:
        return "0m"
    days = seconds // 86400
    seconds %= 86400
    hours = seconds // 3600
    seconds %= 3600
    minutes = seconds // 60
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts)


def format_number(n: int | float) -> str:
    """Return a compact number string: 1K, 5M, etc."""
    n = float(n)
    for suffix in ("K", "M", "G", "T"):  # noqa: B007
        if abs(n) < 1000.0:
            break
        n /= 1000.0
    else:
        return f"{n:.1f}T"
    if suffix == "K" and abs(n) < 10:
        return f"{n:.1f}K"
    return f"{int(n)}{suffix}" if n == int(n) else f"{n:.1f}{suffix}"


_MD_SPECIAL = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")


def escape_md(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    return _MD_SPECIAL.sub(r"\\\1", text)
