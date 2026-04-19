from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from mtproxymaxpy import geoblock

if TYPE_CHECKING:
    from pathlib import Path


def test_run_and_require_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(geoblock.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stderr=""))
    geoblock._run("echo", "ok")

    monkeypatch.setattr(geoblock.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    with pytest.raises(RuntimeError, match="Command not found"):
        geoblock._run("missing")

    monkeypatch.setattr(
        geoblock.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(subprocess.CalledProcessError(1, ["x"], stderr="bad")),
    )
    with pytest.raises(RuntimeError, match="failed"):
        geoblock._run("x")

    monkeypatch.setitem(sys.modules, "shutil", SimpleNamespace(which=lambda t: "/bin/x"))
    geoblock._require_tools()
    monkeypatch.setitem(sys.modules, "shutil", SimpleNamespace(which=lambda t: None))
    with pytest.raises(RuntimeError, match="not found"):
        geoblock._require_tools()


def test_ipset_name_and_download_cidrs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert geoblock._ipset_name("RU").endswith("-ru")

    cache_dir = tmp_path / "geo"
    monkeypatch.setattr(geoblock, "GEO_CACHE_DIR", cache_dir)
    monkeypatch.setattr(geoblock, "GEO_CACHE_TTL", 999999)
    cache_dir.mkdir(parents=True, exist_ok=True)
    f = cache_dir / "ru.zone"
    f.write_text("1.1.1.0/24\n2.2.2.0/24\n", encoding="utf-8")
    out = geoblock._download_cidrs("RU")
    assert out == ["1.1.1.0/24", "2.2.2.0/24"]

    monkeypatch.setattr(geoblock, "GEO_CACHE_TTL", -1)

    class _Resp:
        text = "3.3.3.0/24\n"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(geoblock.httpx, "get", lambda *a, **k: _Resp())
    out = geoblock._download_cidrs("RU")
    assert out == ["3.3.3.0/24"]

    monkeypatch.setattr(geoblock.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="Failed to download"):
        geoblock._download_cidrs("RU")


def test_state_load_save_and_country_ops(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    install = tmp_path / "install"
    install.mkdir()
    state_file = install / "geoblock.json"
    monkeypatch.setattr(geoblock, "INSTALL_DIR", install)
    monkeypatch.setattr(geoblock, "GEO_STATE_FILE", state_file)

    assert geoblock._load_state() == {"countries": [], "mode": "blacklist"}
    state_file.write_text("bad", encoding="utf-8")
    assert geoblock._load_state() == {"countries": [], "mode": "blacklist"}

    geoblock._save_state({"countries": ["RU"], "mode": "blacklist"})
    assert "RU" in geoblock._load_state()["countries"]

    monkeypatch.setattr(geoblock, "_require_tools", lambda: None)
    monkeypatch.setattr(geoblock, "_download_cidrs", lambda cc: ["1.1.1.0/24"])
    calls: list[tuple] = []
    monkeypatch.setattr(geoblock, "_run", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(geoblock.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1))

    n = geoblock.add_country("ru")
    assert n == 1
    assert any("-I" in c[0] for c in calls)
    assert "RU" in geoblock.list_countries()

    monkeypatch.setattr(geoblock.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    geoblock.add_country("ru")
    assert geoblock.list_countries().count("RU") == 1

    geoblock.remove_country("ru")
    assert "RU" not in geoblock.list_countries()


def test_clear_and_reapply_swallow_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(geoblock, "list_countries", lambda: ["RU", "US"])
    touched = {"rm": 0, "add": 0}

    def _rm(cc):
        touched["rm"] += 1
        if cc == "US":
            raise RuntimeError("x")

    def _add(cc):
        touched["add"] += 1
        if cc == "US":
            raise RuntimeError("x")

    monkeypatch.setattr(geoblock, "remove_country", _rm)
    monkeypatch.setattr(geoblock, "add_country", _add)
    geoblock.clear_all()
    geoblock.reapply_all()
    assert touched["rm"] == 2
    assert touched["add"] == 2
