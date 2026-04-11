"""Tests for Secret persistence and CRUD operations."""

import json
import stat
import sys
import pytest
from pathlib import Path
from datetime import date

from mtproxymaxpy.config.secrets import (
    Secret,
    add_secret,
    load_secrets,
    remove_secret,
    rotate_secret,
    save_secrets,
)


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "secrets.json"
    items = [
        Secret(label="alice", key="a" * 32),
        Secret(label="bob", key="b" * 32, enabled=False, max_conns=10),
    ]
    save_secrets(items, path)
    loaded = load_secrets(path)
    assert len(loaded) == 2
    assert loaded[0].label == "alice"
    assert loaded[1].enabled is False
    assert loaded[1].max_conns == 10


@pytest.mark.skipif(sys.platform == "win32", reason="Unix permissions not supported on Windows")
def test_file_mode_600(tmp_path: Path) -> None:
    path = tmp_path / "secrets.json"
    save_secrets([], path)
    mode = path.stat().st_mode & 0o777
    assert mode == 0o600


def test_load_missing_returns_empty(tmp_path: Path) -> None:
    assert load_secrets(tmp_path / "none.json") == []


def test_add_secret(tmp_path: Path) -> None:
    path = tmp_path / "secrets.json"
    s = add_secret("carol", path=path)
    assert s.label == "carol"
    assert len(s.key) == 32
    assert load_secrets(path)[0].label == "carol"


def test_add_duplicate_raises(tmp_path: Path) -> None:
    path = tmp_path / "secrets.json"
    add_secret("dave", path=path)
    with pytest.raises(ValueError, match="already exists"):
        add_secret("dave", path=path)


def test_remove_secret(tmp_path: Path) -> None:
    path = tmp_path / "secrets.json"
    add_secret("eve", path=path)
    assert remove_secret("eve", path) is True
    assert load_secrets(path) == []


def test_remove_nonexistent_returns_false(tmp_path: Path) -> None:
    path = tmp_path / "secrets.json"
    assert remove_secret("ghost", path) is False


def test_rotate_changes_key(tmp_path: Path) -> None:
    path = tmp_path / "secrets.json"
    original = add_secret("frank", path=path)
    rotated = rotate_secret("frank", path)
    assert rotated.key != original.key
    assert rotated.label == "frank"


def test_rotate_missing_raises(tmp_path: Path) -> None:
    path = tmp_path / "secrets.json"
    with pytest.raises(KeyError):
        rotate_secret("nobody", path)


def test_order_preserved_after_remove(tmp_path: Path) -> None:
    path = tmp_path / "secrets.json"
    for name in ("a", "b", "c", "d"):
        add_secret(name, path=path)
    remove_secret("b", path)
    labels = [s.label for s in load_secrets(path)]
    assert labels == ["a", "c", "d"]
