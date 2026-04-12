"""Shared pytest fixtures and test session guards."""

from pathlib import Path
import os

import pytest


def _running_in_docker() -> bool:
    # Standard marker file created by Docker.
    if Path("/.dockerenv").exists():
        return True

    # Fallback for container runtimes that expose cgroup hints.
    cgroup = Path("/proc/1/cgroup")
    if not cgroup.exists():
        return False

    text = cgroup.read_text(encoding="utf-8", errors="ignore")
    markers = ("docker", "containerd", "kubepods", "podman")
    return any(m in text for m in markers)


def pytest_sessionstart(session: pytest.Session) -> None:
    if _running_in_docker():
        return

    if os.environ.get("MTPROXYMAXPY_ALLOW_HOST_PYTEST", "") == "1":
        return

    raise pytest.UsageError(
        "Pytest is enforced to run only in Docker.\n"
        "Run: docker compose run --rm test\n"
        "If you really need host execution, set MTPROXYMAXPY_ALLOW_HOST_PYTEST=1."
    )


@pytest.fixture()
def tmp_config(tmp_path: Path) -> Path:
    """Return a tmp_path that can act as the config root."""
    return tmp_path
