from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from mtproxymaxpy.config import instances, secrets, upstreams


def test_instances_roundtrip_and_save_error_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "instances.json"
    data = [instances.Instance(name="a", port=443), instances.Instance(name="b", port=8443, enabled=False)]
    instances.save_instances(data, path)
    loaded = instances.load_instances(path)
    assert [i.name for i in loaded] == ["a", "b"]
    assert loaded[1].enabled is False

    assert instances.load_instances(tmp_path / "missing.json") == []

    monkeypatch.setattr(instances.os, "replace", lambda src, dst: (_ for _ in ()).throw(RuntimeError("replace failed")))
    with pytest.raises(RuntimeError, match="replace failed"):
        instances.save_instances(data, path)


def test_secrets_mutation_flows(tmp_path: Path) -> None:
    path = tmp_path / "secrets.json"

    # Setup: create alice (active) and bob (already expired)
    secrets.add_secret("alice", path=path)
    secrets.add_secret("bob", expires="2000-01-01", path=path)

    en = secrets.disable_secret("alice", path)
    assert en.enabled is False
    en = secrets.enable_secret("alice", path)
    assert en.enabled is True

    upd = secrets.set_secret_limits("alice", max_conns=3, max_ips=2, quota_bytes=1024, expires="2030-01-01", path=path)
    assert upd.max_conns == 3
    assert upd.max_ips == 2
    assert upd.quota_bytes == 1024
    assert upd.expires == "2030-01-01"

    upd2 = secrets.set_secret_note("alice", "hello", path)
    assert upd2.notes == "hello"

    ext = secrets.extend_secret("alice", 5, path)
    assert ext.expires

    all_ext = secrets.bulk_extend_secrets(1, path)
    assert len(all_ext) == 2

    expired = secrets.get_expired_secrets(path)
    assert any(s.label == "bob" for s in expired)

    disabled = secrets.disable_expired_secrets(path)
    assert any(s.label == "bob" for s in disabled)

    rn = secrets.rename_secret("alice", "alice2", path)
    assert rn.label == "alice2"

    cl = secrets.clone_secret("alice2", "alice3", path)
    assert cl.label == "alice3"
    assert cl.key != rn.key

    with pytest.raises(KeyError):
        secrets.set_secret_limits("missing", max_conns=1, path=path)
    with pytest.raises(KeyError):
        secrets.extend_secret("missing", 1, path)
    with pytest.raises(KeyError):
        secrets.rename_secret("missing", "x", path)
    with pytest.raises(KeyError):
        secrets.clone_secret("missing", "x", path)
    with pytest.raises(ValueError, match="already exists"):
        secrets.rename_secret("alice2", "alice3", path)
    with pytest.raises(ValueError, match="already exists"):
        secrets.clone_secret("alice2", "alice3", path)


def test_secrets_csv_import_export_and_save_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "secrets.json"
    secrets.add_secret("alice", path=path)

    csv_text = secrets.export_secrets_csv(path)
    assert "label,key,created" in csv_text
    assert "alice" in csv_text

    to_import = "\n".join(
        [
            "label,key,created,enabled,max_conns,max_ips,quota_bytes,expires,notes",
            "alice," + "a" * 32 + ",2020-01-01,true,1,2,3,2030-01-01,note",
            "bob,,2020-01-01,yes,0,0,0,,",
            "," + "c" * 32 + ",2020-01-01,true,0,0,0,,",
        ],
    )
    added = secrets.import_secrets_csv(to_import, path=path, overwrite=False)
    assert [s.label for s in added] == ["bob"]

    added2 = secrets.import_secrets_csv(to_import, path=path, overwrite=True)
    assert any(s.label == "alice" for s in added2)

    # Save error path cleanup.
    monkeypatch.setattr(secrets.os, "replace", lambda src, dst: (_ for _ in ()).throw(RuntimeError("replace failed")))
    with pytest.raises(RuntimeError, match="replace failed"):
        secrets.save_secrets(secrets.load_secrets(path), path)


def test_secret_model_normalization_branches() -> None:
    assert secrets.Secret(label="x", key="a" * 32, expires=None).expires == ""
    assert secrets.Secret(label="x", key="a" * 32, expires="").expires == ""
    assert secrets.Secret(label="x", key="a" * 32, expires="0").expires == ""
    assert secrets.Secret(label="x", key="a" * 32, expires="2026-01-02").expires == "2026-01-02"
    assert secrets.Secret(label="x", key="a" * 32, expires="2026-01-02T03:04:05Z").expires == "2026-01-02"
    assert secrets.Secret(label="x", key="a" * 32, expires="not-a-date").expires == ""


def test_upstreams_validation_and_mutation_flows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "upstreams.json"

    # load fallbacks
    assert upstreams.load_upstreams(path)[0].name == "direct"
    path.write_text("{bad json", encoding="utf-8")
    assert upstreams.load_upstreams(path)[0].name == "direct"

    # save default direct when empty
    upstreams.save_upstreams([], path)
    assert upstreams.load_upstreams(path)[0].name == "direct"

    # invalid save path cleanup
    monkeypatch.setattr(upstreams.os, "replace", lambda src, dst: (_ for _ in ()).throw(RuntimeError("replace failed")))
    with pytest.raises(RuntimeError, match="replace failed"):
        upstreams.save_upstreams([upstreams.Upstream(name="direct", type="direct")], path)


def test_upstreams_add_remove_enable_disable_test(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "upstreams.json"
    upstreams.save_upstreams([upstreams.Upstream(name="direct", type="direct", enabled=True)], path)

    with pytest.raises(ValueError, match="Name must match"):
        upstreams.add_upstream("bad name", type_="direct", path=path)
    with pytest.raises(ValueError, match="Name must match"):
        upstreams.add_upstream("a" * 33, type_="direct", path=path)
    with pytest.raises(ValueError, match="Type must be"):
        upstreams.add_upstream("u1", type_="bad", path=path)
    with pytest.raises(ValueError, match="is required"):
        upstreams.add_upstream("u1", type_="socks5", addr="", path=path)
    with pytest.raises(ValueError, match="host:port format"):
        upstreams.add_upstream("u1", type_="socks5", addr="host:notnum", path=path)
    with pytest.raises(ValueError, match="Port must be"):
        upstreams.add_upstream("u1", type_="socks5", addr="host:99999", path=path)
    with pytest.raises(ValueError, match="cannot contain"):
        upstreams.add_upstream("u1", type_="socks5", addr="h:1080", user="bad|x", path=path)
    with pytest.raises(ValueError, match="cannot contain"):
        upstreams.add_upstream("u1", type_="socks5", addr="h:1080", password='bad"x', path=path)
    with pytest.raises(ValueError, match="cannot contain"):
        upstreams.add_upstream("u1", type_="socks5", addr="h:1080", iface="bad\\x", path=path)
    with pytest.raises(ValueError, match="Weight must be"):
        upstreams.add_upstream("u1", type_="socks5", addr="h:1080", weight=101, path=path)

    u1 = upstreams.add_upstream("u1", type_="socks4", addr="127.0.0.1:1080", password="x", path=path)
    assert u1.password == ""
    with pytest.raises(ValueError, match="already exists"):
        upstreams.add_upstream("u1", type_="direct", path=path)

    # field setter path
    changed = upstreams._set_upstream_field("u1", "weight", value=7, path=path)
    assert changed.weight == 7
    with pytest.raises(KeyError):
        upstreams._set_upstream_field("missing", "weight", value=1, path=path)

    # remove/disable guards
    upstreams.disable_upstream("u1", path)
    with pytest.raises(ValueError, match="Cannot remove"):
        upstreams.remove_upstream("direct", path)
    upstreams.enable_upstream("u1", path)
    upstreams.disable_upstream("direct", path)
    with pytest.raises(ValueError, match="Cannot disable"):
        upstreams.disable_upstream("u1", path)
    with pytest.raises(KeyError):
        upstreams.set_upstream_enabled("missing", enabled=True, path=path)
    with pytest.raises(KeyError):
        upstreams.toggle_upstream("missing", path)

    # keep one enabled and remove another
    upstreams.enable_upstream("direct", path)
    upstreams.remove_upstream("u1", path)

    # test_upstream branches
    monkeypatch.setattr("shutil.which", lambda _: None)
    out = upstreams.test_upstream("direct")
    assert out["ok"] is None

    monkeypatch.setattr("shutil.which", lambda _: "curl")
    monkeypatch.setattr("subprocess.run", lambda *a, **k: SimpleNamespace(returncode=0, stderr=""))
    ok = upstreams.test_upstream("direct")
    assert ok["ok"] is True
    assert ok["latency_ms"] is not None

    monkeypatch.setattr("subprocess.run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    bad = upstreams.test_upstream("direct")
    assert bad["ok"] is False
    assert "boom" in (bad["error"] or "")

    with pytest.raises(KeyError):
        upstreams.test_upstream("missing")
