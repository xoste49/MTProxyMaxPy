from __future__ import annotations

import io
import json
import tarfile

import pytest

from mtproxymaxpy import backup
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def test_create_backup_includes_configs_stats_and_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_dir = tmp_path / "install"
    backup_dir = tmp_path / "backups"
    install_dir.mkdir()

    settings = install_dir / "settings.toml"
    secrets = install_dir / "secrets.json"
    upstreams = install_dir / "upstreams.json"
    instances = install_dir / "instances.json"
    for p, content in (
        (settings, "a=1\n"),
        (secrets, "{}\n"),
        (upstreams, "[]\n"),
        (instances, "[]\n"),
    ):
        p.write_text(content, encoding="utf-8")

    stats_dir = install_dir / "relay_stats"
    stats_dir.mkdir()
    (stats_dir / "snapshot.json").write_text('{"ok":true}', encoding="utf-8")

    monkeypatch.setattr(backup, "INSTALL_DIR", install_dir)
    monkeypatch.setattr(backup, "BACKUP_DIR", backup_dir)
    monkeypatch.setattr(backup, "SETTINGS_FILE", settings)
    monkeypatch.setattr(backup, "SECRETS_FILE", secrets)
    monkeypatch.setattr(backup, "UPSTREAMS_FILE", upstreams)
    monkeypatch.setattr(backup, "INSTANCES_FILE", instances)

    archive = backup.create_backup("manual")
    assert archive.exists()
    assert "-manual" in archive.name

    with tarfile.open(archive, "r:gz") as tf:
        names = set(tf.getnames())
        assert "settings.toml" in names
        assert "secrets.json" in names
        assert "upstreams.json" in names
        assert "instances.json" in names
        assert "relay_stats" in names
        assert "relay_stats/snapshot.json" in names
        assert "metadata.json" in names

        meta = json.loads(tf.extractfile("metadata.json").read())  # type: ignore[arg-type]
        assert "version" in meta
        assert "date" in meta
        assert "hostname" in meta
        assert "platform" in meta


def test_list_backups_empty_when_dir_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path / "missing")
    assert backup.list_backups() == []


def test_restore_backup_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        backup.restore_backup(tmp_path / "nope.tar.gz")


def test_restore_backup_extracts_and_returns_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_dir = tmp_path / "install"
    install_dir.mkdir()

    settings = install_dir / "settings.toml"
    secrets = install_dir / "secrets.json"
    settings.write_text("old=1\n", encoding="utf-8")
    secrets.write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(backup, "INSTALL_DIR", install_dir)
    monkeypatch.setattr(backup, "SETTINGS_FILE", settings)
    monkeypatch.setattr(backup, "SECRETS_FILE", secrets)
    monkeypatch.setattr(backup, "UPSTREAMS_FILE", install_dir / "upstreams.json")
    monkeypatch.setattr(backup, "INSTANCES_FILE", install_dir / "instances.json")

    pre = tmp_path / "pre-restore.tar.gz"
    called: list[str] = []

    def _fake_create_backup(label: str) -> Path:
        called.append(label)
        return pre

    monkeypatch.setattr(backup, "create_backup", _fake_create_backup)

    archive = tmp_path / "restore.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        meta = {"source": "test"}
        raw = json.dumps(meta).encode("utf-8")
        info = tarfile.TarInfo("metadata.json")
        info.size = len(raw)
        tf.addfile(info, io.BytesIO(raw))

        payload = b"new=2\n"
        info = tarfile.TarInfo("settings.toml")
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))

        payload = b'{"a":1}\n'
        info = tarfile.TarInfo("secrets.json")
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))

        relay_dir = tarfile.TarInfo("relay_stats")
        relay_dir.type = tarfile.DIRTYPE
        tf.addfile(relay_dir)

    meta = backup.restore_backup(archive)
    assert called == ["pre-restore"]
    assert settings.read_text(encoding="utf-8") == "new=2\n"
    assert secrets.read_text(encoding="utf-8") == '{"a":1}\n'
    assert (install_dir / "relay_stats").exists()
    assert meta["source"] == "test"
    assert meta["pre_restore_backup"] == str(pre)


def test_restore_backup_without_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    monkeypatch.setattr(backup, "INSTALL_DIR", install_dir)
    monkeypatch.setattr(backup, "SETTINGS_FILE", install_dir / "settings.toml")
    monkeypatch.setattr(backup, "SECRETS_FILE", install_dir / "secrets.json")

    archive = tmp_path / "restore-no-meta.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        payload = b"x=1\n"
        info = tarfile.TarInfo("settings.toml")
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))

    meta = backup.restore_backup(archive)
    assert meta["pre_restore_backup"] is None
