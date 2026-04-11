"""Shared pytest fixtures."""

import pytest
from pathlib import Path


@pytest.fixture()
def tmp_config(tmp_path: Path) -> Path:
    """Return a tmp_path that can act as the config root."""
    return tmp_path
