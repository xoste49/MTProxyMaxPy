from __future__ import annotations

import io
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer

from mtproxymaxpy import cli


class FakeSettings:
    def __init__(self, **kwargs):
        self.proxy_port = kwargs.get("proxy_port", 443)
        self.proxy_domain = kwargs.get("proxy_domain", "cloudflare.com")
        self.custom_ip = kwargs.get("custom_ip", "")
        self.ad_tag = kwargs.get("ad_tag", "")
        self.unknown_sni_action = kwargs.get("unknown_sni_action", "mask")
        self.telegram_enabled = kwargs.get("telegram_enabled", False)
        self.telegram_bot_token = kwargs.get("telegram_bot_token", "")
        self.telegram_chat_id = kwargs.get("telegram_chat_id", "")
        self.telegram_interval = kwargs.get("telegram_interval", 24)
        self.telegram_alerts_enabled = kwargs.get("telegram_alerts_enabled", True)
        self.telegram_server_label = kwargs.get("telegram_server_label", "srv")
        self.manager_update_branch = kwargs.get("manager_update_branch", "main")

    def model_copy(self, update: dict):
        data = self.__dict__.copy()
        data.update(update)
        return FakeSettings(**data)


class FakeSecret:
    def __init__(self, label: str, key: str = "a" * 32, enabled: bool = True):
        self.label = label
        self.key = key
        self.enabled = enabled
        self.max_conns = 0
        self.max_ips = 0
        self.quota_bytes = 0
        self.expires = ""
        self.notes = ""


class FakeUpstream:
    def __init__(self, name: str, type_: str = "socks5", addr: str = "127.0.0.1:1080", enabled: bool = True):
        self.name = name
        self.type = type_
        self.addr = addr
        self.weight = 10
        self.enabled = enabled


def _set_pkg_module(monkeypatch: pytest.MonkeyPatch, name: str, mod: object) -> None:
    import mtproxymaxpy as pkg

    monkeypatch.setitem(sys.modules, f"mtproxymaxpy.{name}", mod)
    monkeypatch.setattr(pkg, name, mod, raising=False)


def test_core_proxy_commands_and_status(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    saved: list[FakeSettings] = []
    settings = FakeSettings(proxy_port=443, proxy_domain="cloudflare.com")

    set_mod = SimpleNamespace(load_settings=lambda: settings, save_settings=lambda s: saved.append(s), Settings=FakeSettings)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.config.settings", set_mod)
    mig_mod = SimpleNamespace(detect_legacy=list, run_migration=lambda _: None)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.config.migration", mig_mod)

    pm = SimpleNamespace(
        download_binary=lambda **k: None,
        start=lambda public_ip="": 11,
        stop=lambda: None,
        restart=lambda public_ip="": 22,
        reload_config=lambda: None,
        status=lambda: {"running": True, "pid": 123, "uptime_sec": 61},
        is_running=lambda: True,
        get_latest_version=lambda: "v1",
    )
    _set_pkg_module(monkeypatch, "process_manager", pm)
    _set_pkg_module(monkeypatch, "systemd", SimpleNamespace(install=lambda: None, uninstall=lambda telegram=True: None))
    _set_pkg_module(
        monkeypatch,
        "metrics",
        SimpleNamespace(
            get_stats=lambda: {
                "available": True,
                "bytes_in": 1,
                "bytes_out": 2,
                "active_connections": 3,
                "total_connections": 4,
            },
        ),
    )
    sec_mod = SimpleNamespace(load_secrets=lambda: [FakeSecret("u1", enabled=True), FakeSecret("u2", enabled=False)])
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.config.secrets", sec_mod)
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.utils.system",
        SimpleNamespace(check_root=lambda: None, check_dependencies=lambda: None),
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.network", SimpleNamespace(get_public_ip=lambda: "1.2.3.4"))
    monkeypatch.setattr(cli, "VERSION", "X")
    monkeypatch.setattr(typer, "confirm", lambda *a, **k: True)
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.constants",
        SimpleNamespace(
            SETTINGS_FILE=Path("missing.toml"),
            INSTALL_DIR=Path("x"),
            VERSION="X",
            BACKUP_DIR=Path(),
            STATS_DIR=Path(),
        ),
    )

    cli.install(port=8443, domain="example.com", systemd=False)
    out = capsys.readouterr().out
    assert "Installation complete" in out
    assert saved
    assert saved[-1].proxy_port == 8443

    cli.start()
    cli.stop()
    cli.restart()
    cli.reload()
    out = capsys.readouterr().out
    assert "started" in out
    assert "restarted" in out

    cli.status(output_json=False)
    txt = capsys.readouterr().out
    assert "running=True" in txt

    cli.status(output_json=True)
    txt = capsys.readouterr().out
    assert '"port": 443' in txt

    cli.update()
    assert "Binary updated" in capsys.readouterr().out


def test_doctor_health_logs_metrics_connections_traffic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _set_pkg_module(
        monkeypatch,
        "doctor",
        SimpleNamespace(run_full_doctor=lambda: [{"name": "A", "ok": True}, {"name": "B", "ok": None}]),
    )
    cli.doctor()
    assert "A" in capsys.readouterr().out

    _set_pkg_module(monkeypatch, "doctor", SimpleNamespace(run_full_doctor=lambda: [{"name": "C", "ok": False}]))
    with pytest.raises(typer.Exit):
        cli.doctor()

    _set_pkg_module(monkeypatch, "process_manager", SimpleNamespace(is_running=lambda: True))
    cli.health()
    assert "healthy" in capsys.readouterr().out

    _set_pkg_module(monkeypatch, "process_manager", SimpleNamespace(is_running=lambda: False))
    with pytest.raises(typer.Exit):
        cli.health()

    log_file = tmp_path / "telemt.log"
    log_file.write_text("hello", encoding="utf-8")
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.constants",
        SimpleNamespace(INSTALL_DIR=tmp_path, STATS_DIR=tmp_path, BACKUP_DIR=tmp_path),
    )
    calls: list[list[str]] = []
    monkeypatch.setitem(sys.modules, "subprocess", SimpleNamespace(run=lambda cmd: calls.append(cmd)))
    cli.logs(lines=5, follow=False)
    cli.logs(lines=5, follow=True)
    assert calls[0][0] == "tail"
    assert calls[1][1] == "-f"

    log_file.unlink()
    with pytest.raises(typer.Exit):
        cli.logs()

    _set_pkg_module(monkeypatch, "metrics", SimpleNamespace(get_stats=lambda: {"available": False, "error": "x"}))
    with pytest.raises(typer.Exit):
        cli.metrics()

    _set_pkg_module(
        monkeypatch,
        "metrics",
        SimpleNamespace(
            get_stats=lambda: {
                "available": True,
                "bytes_in": 1,
                "bytes_out": 2,
                "active_connections": 3,
                "total_connections": 4,
                "user_stats": {"k": {"bytes_in": 1, "bytes_out": 2, "active": 1}},
            },
        ),
    )
    cli.metrics()
    assert "Per-user" in capsys.readouterr().out

    cli.traffic()
    assert "bytes_in" in capsys.readouterr().out

    cli.connections()
    assert "Active connections" in capsys.readouterr().out


def test_settings_commands(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    settings = FakeSettings(proxy_port=443, proxy_domain="cf.com", custom_ip="", ad_tag="")
    saved: list[FakeSettings] = []
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(load_settings=lambda: settings, save_settings=lambda s: saved.append(s)),
    )

    cli.port(None)
    assert "443" in capsys.readouterr().out
    cli.port(8443)
    assert saved[-1].proxy_port == 8443
    with pytest.raises(typer.Exit):
        cli.port(70000)

    cli.domain(None)
    cli.domain("clear")
    cli.domain("example.com")
    assert saved[-1].proxy_domain == "example.com"

    cli.ip(None)
    cli.ip("auto")
    cli.ip("8.8.8.8")
    assert saved[-1].custom_ip == "8.8.8.8"

    cli.adtag("view")
    cli.adtag("set", "TAG")
    cli.adtag("remove")
    with pytest.raises(typer.Exit):
        cli.adtag("set", None)
    with pytest.raises(typer.Exit):
        cli.adtag("bad", "x")

    cli.sni_policy(None)
    cli.sni_policy("drop")
    assert saved[-1].unknown_sni_action == "drop"
    with pytest.raises(typer.Exit):
        cli.sni_policy("oops")

    cli.manager_branch(None)
    assert "main" in capsys.readouterr().out
    cli.manager_branch("develop")
    assert saved[-1].manager_update_branch == "develop"
    with pytest.raises(typer.Exit):
        cli.manager_branch(" ")
    with pytest.raises(typer.Exit):
        cli.manager_branch("bad branch")


def test_secret_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    restarted = {"n": 0}
    monkeypatch.setattr(cli, "_restart_if_running", lambda: restarted.__setitem__("n", restarted["n"] + 1))

    secrets = [FakeSecret("alice", key="a" * 32, enabled=True), FakeSecret("bob", key="b" * 32, enabled=False)]
    sec_mod = SimpleNamespace(
        add_secret=lambda *a, **k: FakeSecret(a[0], key="c" * 32),
        load_secrets=lambda: secrets,
        remove_secret=lambda label: label == "alice",
        rotate_secret=lambda label: FakeSecret(label, key="d" * 32),
        enable_secret=lambda label: None,
        disable_secret=lambda label: None,
        set_secret_limits=lambda *a, **k: None,
        extend_secret=lambda label, days: SimpleNamespace(expires="2099-01-01"),
        bulk_extend_secrets=lambda days: ["alice"],
        disable_expired_secrets=lambda: ["bob"],
        rename_secret=lambda old, new: None,
        clone_secret=lambda src, new: FakeSecret(new, key="e" * 32),
        set_secret_note=lambda label, text: None,
        export_secrets_csv=lambda: "label,key\na,a\n",
        import_secrets_csv=lambda text, overwrite=False: [FakeSecret("x")],
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.config.secrets", sec_mod)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.validation", SimpleNamespace(parse_human_bytes=lambda x: 1024))
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(load_settings=lambda: FakeSettings(proxy_port=443, proxy_domain="cf.com", custom_ip="")),
    )
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.utils.proxy_link",
        SimpleNamespace(build_proxy_links=lambda *a, **k: ("tg://x", "https://x"), render_qr_terminal=lambda s: "##QR##"),
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.network", SimpleNamespace(get_public_ip=lambda: "1.1.1.1"))
    _set_pkg_module(
        monkeypatch,
        "metrics",
        SimpleNamespace(
            get_stats=lambda: {
                "available": True,
                "user_stats": {"a" * 32: {"bytes_in": 1, "bytes_out": 2, "active": 1}},
            },
        ),
    )

    stats_dir = tmp_path / "relay_stats"
    stats_dir.mkdir()
    (stats_dir / ("a" * 32 + "-1.json")).write_text("x", encoding="utf-8")
    (stats_dir / ("x.json")).write_text("x", encoding="utf-8")
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.constants",
        SimpleNamespace(
            STATS_DIR=stats_dir,
            BACKUP_DIR=tmp_path,
            INSTALL_DIR=tmp_path,
            SETTINGS_FILE=tmp_path / "s.toml",
            VERSION="X",
        ),
    )

    cli.secret_add("new")
    cli.secret_add_batch(["x", "y"])
    cli.secret_list()
    cli.secret_remove("alice")
    with pytest.raises(typer.Exit):
        cli.secret_remove("missing")
    cli.secret_rotate("alice")
    cli.secret_enable("alice")
    cli.secret_disable("alice")
    cli.secret_limits("alice")
    with pytest.raises(typer.Exit):
        cli.secret_limits("missing")
    cli.secret_setlimit("alice", "conns", "5")
    cli.secret_setlimit("alice", "ips", "2")
    cli.secret_setlimit("alice", "quota", "1G")
    cli.secret_setlimit("alice", "expires", "2030-01-01")
    with pytest.raises(typer.Exit):
        cli.secret_setlimit("alice", "bad", "1")
    cli.secret_extend("alice", 10)
    cli.secret_bulk_extend(5)
    cli.secret_disable_expired()
    cli.secret_rename("alice", "alice2")
    cli.secret_clone("alice", "alice3")
    cli.secret_note("alice", "note")
    cli.secret_link("alice")
    cli.secret_qr("alice")
    cli.secret_stats()
    cli.secret_reset_traffic(None)
    cli.secret_reset_traffic("alice")
    cli.secret_export()
    cli.secret_import(io.StringIO("label,key\nx,1\n"), overwrite=False)
    assert restarted["n"] > 0

    sec_mod.rotate_secret = lambda label: (_ for _ in ()).throw(KeyError("no"))
    with pytest.raises(typer.Exit):
        cli.secret_rotate("missing")

    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.utils.proxy_link",
        SimpleNamespace(build_proxy_links=lambda *a, **k: ("tg://x", "https://x"), render_qr_terminal=lambda s: ""),
    )
    cli.secret_qr("alice")

    _set_pkg_module(monkeypatch, "metrics", SimpleNamespace(get_stats=lambda: {"available": False, "error": "x"}))
    with pytest.raises(typer.Exit):
        cli.secret_stats()


def test_upstream_backup_geo_telegram_and_misc(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(cli, "_restart_if_running", lambda: None)
    ups_mod = SimpleNamespace(
        add_upstream=lambda *a, **k: None,
        load_upstreams=lambda: [FakeUpstream("u1")],
        remove_upstream=lambda name: None,
        enable_upstream=lambda name: None,
        disable_upstream=lambda name: None,
        test_upstream=lambda name: {"ok": True, "latency_ms": 12},
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.config.upstreams", ups_mod)

    cli.upstream_add("u")
    cli.upstream_list()
    cli.upstream_remove("u")
    cli.upstream_enable("u")
    cli.upstream_disable("u")
    cli.upstream_test("u")
    ups_mod.test_upstream = lambda name: {"ok": False, "error": "bad"}
    with pytest.raises(typer.Exit):
        cli.upstream_test("u")

    bmod = SimpleNamespace(
        create_backup=lambda label="": tmp_path / "b.tar.gz",
        list_backups=lambda: [{"mtime": datetime(2026, 1, 1, tzinfo=UTC), "size": 1024, "name": "b.tar.gz"}],
        restore_backup=lambda path: {"version": "1", "date": "now", "pre_restore_backup": "pre.tar.gz"},
    )
    _set_pkg_module(monkeypatch, "backup", bmod)
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.constants",
        SimpleNamespace(
            BACKUP_DIR=tmp_path,
            INSTALL_DIR=tmp_path,
            STATS_DIR=tmp_path,
            SETTINGS_FILE=tmp_path / "s.toml",
            VERSION="X",
        ),
    )
    cli.backup_create("x")
    cli.backup_list()
    cli.backup_restore("b.tar.gz", yes=True)
    out = capsys.readouterr().out
    assert "Restored" in out

    gmod = SimpleNamespace(add_country=lambda cc: 5, remove_country=lambda cc: None, list_countries=lambda: ["RU"], clear_all=lambda: None)
    _set_pkg_module(monkeypatch, "geoblock", gmod)
    cli.geoblock_add("ru")
    cli.geoblock_remove("ru")
    cli.geoblock_list()
    cli.geoblock_clear(yes=True)

    settings = FakeSettings(telegram_enabled=True, telegram_bot_token="tok", telegram_chat_id="1")
    saved: list[FakeSettings] = []
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(load_settings=lambda: settings, save_settings=lambda s: saved.append(s)),
    )

    class _AioBot:
        def __init__(self, token: str):
            self.token = token

            async def _close() -> None:
                return None

            self.session = SimpleNamespace(close=_close)

        async def send_message(self, chat_id: str, text: str):
            return None

    monkeypatch.setitem(sys.modules, "aiogram", SimpleNamespace(Bot=_AioBot))
    cli.telegram_status()
    cli.telegram_test()
    cli.telegram_disable()
    cli.telegram_enable()
    assert saved[-1].telegram_enabled is True

    settings2 = FakeSettings(telegram_enabled=False, telegram_bot_token="", telegram_chat_id="")
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(load_settings=lambda: settings2, save_settings=lambda s: saved.append(s)),
    )
    with pytest.raises(typer.Exit):
        cli.telegram_test()
    with pytest.raises(typer.Exit):
        cli.telegram_enable()
    monkeypatch.setitem(sys.modules, "signal", SimpleNamespace(pause=lambda: (_ for _ in ()).throw(KeyboardInterrupt())))
    settings_aiogram = FakeSettings(telegram_enabled=True, telegram_bot_token="tok", telegram_chat_id="1")
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(load_settings=lambda: settings_aiogram, save_settings=lambda s: saved.append(s)),
    )
    aiogram_calls = {"start": 0, "stop": 0}
    _set_pkg_module(
        monkeypatch,
        "telegram_bot_aiogram",
        SimpleNamespace(
            start=lambda: aiogram_calls.__setitem__("start", aiogram_calls["start"] + 1),
            stop=lambda: aiogram_calls.__setitem__("stop", aiogram_calls["stop"] + 1),
        ),
    )
    cli.run_telegram_bot()
    assert aiogram_calls == {"start": 1, "stop": 1}

    cli.version()
    assert "MTProxyMaxPy" in capsys.readouterr().out


def test_restart_if_running_branches(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    pm = SimpleNamespace(is_running=lambda: True, restart=lambda public_ip="": 99, write_toml_config=lambda: None)
    _set_pkg_module(monkeypatch, "process_manager", pm)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.network", SimpleNamespace(get_public_ip=lambda: "1.1.1.1"))
    cli._restart_if_running()
    assert "restarted" in capsys.readouterr().out

    pm2 = SimpleNamespace(
        is_running=lambda: False,
        restart=lambda public_ip="": 0,
        write_toml_config=lambda: (_ for _ in ()).throw(RuntimeError("x")),
    )
    _set_pkg_module(monkeypatch, "process_manager", pm2)
    cli._restart_if_running()
