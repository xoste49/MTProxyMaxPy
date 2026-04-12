"""Tests for Upstream persistence."""

import sys
import pytest
from pathlib import Path

from mtproxymaxpy.config.upstreams import (
    Upstream,
    add_upstream,
    disable_upstream,
    enable_upstream,
    load_upstreams,
    remove_upstream,
    save_upstreams,
    toggle_upstream,
)


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


def test_missing_returns_default_direct(tmp_path: Path) -> None:
    items = load_upstreams(tmp_path / "none.json")
    assert len(items) == 1
    assert items[0].name == "direct"
    assert items[0].type == "direct"
    assert items[0].enabled is True


@pytest.mark.skipif(sys.platform == "win32", reason="Unix permissions not supported on Windows")
def test_file_mode_600(tmp_path: Path) -> None:
    path = tmp_path / "upstreams.json"
    save_upstreams([], path)
    mode = path.stat().st_mode & 0o777
    assert mode == 0o600


def test_invalid_type_raises() -> None:
    with pytest.raises(Exception):
        Upstream(name="bad", type="ftp")  # type: ignore[arg-type]


def test_cannot_disable_last_enabled_upstream(tmp_path: Path) -> None:
    path = tmp_path / "upstreams.json"
    save_upstreams([Upstream(name="direct", type="direct", enabled=True)], path)
    with pytest.raises(ValueError, match="last enabled"):
        disable_upstream("direct", path)


def test_cannot_remove_last_enabled_upstream(tmp_path: Path) -> None:
    path = tmp_path / "upstreams.json"
    save_upstreams([Upstream(name="direct", type="direct", enabled=True)], path)
    with pytest.raises(ValueError, match="last upstream"):
        remove_upstream("direct", path)


def test_add_upstream_validates_addr_and_name(tmp_path: Path) -> None:
    path = tmp_path / "upstreams.json"
    with pytest.raises(ValueError, match=r"Address \(host:port\) is required"):
        add_upstream("node1", type_="socks5", addr="", path=path)
    with pytest.raises(ValueError, match="Name must match"):
        add_upstream("bad name", type_="direct", path=path)


def test_add_and_remove_flow_with_guards(tmp_path: Path) -> None:
    path = tmp_path / "upstreams.json"
    add_upstream("node1", type_="socks5", addr="127.0.0.1:1080", path=path)
    enable_upstream("node1", path)
    remove_upstream("direct", path)
    loaded = load_upstreams(path)
    assert len(loaded) == 1
    assert loaded[0].name == "node1"


def test_toggle_upstream_changes_state(tmp_path: Path) -> None:
    path = tmp_path / "upstreams.json"
    save_upstreams([
        Upstream(name="direct", type="direct", enabled=True),
        Upstream(name="node1", type="socks5", addr="127.0.0.1:1080", enabled=True),
    ], path)
    updated = toggle_upstream("node1", path)
    assert updated.enabled is False
    updated = toggle_upstream("node1", path)
    assert updated.enabled is True
