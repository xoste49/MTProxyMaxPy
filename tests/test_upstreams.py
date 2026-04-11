"""Tests for Upstream persistence."""

import sys
import pytest
from pathlib import Path

from mtproxymaxpy.config.upstreams import Upstream, load_upstreams, save_upstreams


def test_save_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "upstreams.json"
    items = [
        Upstream(name="direct", type="direct"),
        Upstream(name="socks1", type="socks5", addr="127.0.0.1:1080", weight=80),
    ]
    save_upstreams(items, path)
    loaded = load_upstreams(path)
    assert len(loaded) == 2
    assert loaded[1].addr == "127.0.0.1:1080"
    assert loaded[1].weight == 80


def test_missing_returns_empty(tmp_path: Path) -> None:
    assert load_upstreams(tmp_path / "none.json") == []


@pytest.mark.skipif(sys.platform == "win32", reason="Unix permissions not supported on Windows")
def test_file_mode_600(tmp_path: Path) -> None:
    path = tmp_path / "upstreams.json"
    save_upstreams([], path)
    mode = path.stat().st_mode & 0o777
    assert mode == 0o600


def test_invalid_type_raises() -> None:
    with pytest.raises(Exception):
        Upstream(name="bad", type="ftp")  # type: ignore[arg-type]
