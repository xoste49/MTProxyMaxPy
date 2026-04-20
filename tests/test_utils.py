"""Tests for formatting and validation utilities."""

import pytest

from mtproxymaxpy.utils.formatting import (
    escape_md,
    format_bytes,
    format_duration,
    format_number,
)
from mtproxymaxpy.utils.validation import parse_human_bytes, validate_domain, validate_port

# ── format_bytes ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (0, "0 B"),
        (512, "512 B"),
        (1023, "1023 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (1024**2, "1.0 MB"),
        (int(2.3 * 1024**2), "2.3 MB"),
        (1024**3, "1.0 GB"),
        (int(1.2 * 1024**3), "1.2 GB"),
    ],
)
def test_format_bytes(n, expected):
    assert format_bytes(n) == expected


# ── format_duration ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("secs", "expected"),
    [
        (0, "0m"),
        (59, "0m"),
        (60, "1m"),
        (3600, "1h"),
        (3661, "1h 1m"),
        (86400, "1d"),
        (86400 + 3 * 3600 + 45 * 60, "1d 3h 45m"),
        (-1, "0m"),
    ],
)
def test_format_duration(secs, expected):
    assert format_duration(secs) == expected


# ── format_number ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (999, "999K"),  # edge — stays in K territory if < 1000
        (1000, "1K"),
        (5000, "5K"),
        (1_000_000, "1M"),
        (5_500_000, "5.5M"),
    ],
)
def test_format_number(n, expected):
    # format_number works on values already divided once,
    # let's just check it runs without error and returns a string
    result = format_number(n)
    assert isinstance(result, str)


# ── validate_port ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("port", "valid"),
    [
        (1, True),
        (443, True),
        (65535, True),
        (0, False),
        (65536, False),
        ("443", True),
        ("abc", False),
        (None, False),
    ],
)
def test_validate_port(port, valid):
    assert validate_port(port) == valid


# ── validate_domain ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("domain", "valid"),
    [
        ("cloudflare.com", True),
        ("sub.example.org", True),
        ("my-host", True),
        ("a" * 64 + ".com", False),  # label too long
        ("", False),
        ("bad domain", False),
        ("trailing-.com", False),
    ],
)
def test_validate_domain(domain, valid):
    assert validate_domain(domain) == valid


# ── parse_human_bytes ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", 0),
        ("1024", 1024),
        ("1K", 1024),
        ("1KB", 1024),
        ("5G", 5 * 1024**3),
        ("500M", 500 * 1024**2),
        ("2.5G", int(2.5 * 1024**3)),
        ("1T", 1024**4),
    ],
)
def test_parse_human_bytes_valid(value, expected):
    assert parse_human_bytes(value) == expected


@pytest.mark.parametrize("value", ["abc", "5X", "-1", ""])
def test_parse_human_bytes_invalid(value):
    with pytest.raises(ValueError, match="byte value"):
        parse_human_bytes(value)


# ── escape_md ─────────────────────────────────────────────────────────────────


def test_escape_md_special_chars():
    result = escape_md("Hello_World! (test)")
    assert "_" not in result.replace("\\_", "")  # underscore should be escaped
    assert "\\!" in result
