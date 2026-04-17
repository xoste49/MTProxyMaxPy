from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from mtproxymaxpy.tui import menu


def _mute_ui(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(menu, "_clear", lambda: None)
    monkeypatch.setattr(menu, "_pause", lambda: None)
    monkeypatch.setattr(menu, "_header_panel", lambda: "H")
    monkeypatch.setattr(menu.console, "print", lambda *a, **k: None)


def test_update_screen_deep_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _mute_ui(monkeypatch)
    import mtproxymaxpy as pkg

    install_dir = tmp_path / "install"
    install_dir.mkdir()
    sha_file = tmp_path / "sha"
    badge_file = tmp_path / "badge"

    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.constants",
        SimpleNamespace(
            GITHUB_REPO="owner/repo",
            GITHUB_API_COMMITS="https://api.example/commits",
            INSTALL_DIR=install_dir,
            UPDATE_SHA_FILE=sha_file,
            UPDATE_BADGE_FILE=badge_file,
            VERSION="1.0.0",
            TELEMT_VERSION="1.0.0",
            SYSTEMD_TELEGRAM_SERVICE="mtproxymaxpy-telegram",
        ),
    )

    _pm = SimpleNamespace(
        get_latest_version=lambda: "1.0.0",
        is_running=lambda: False,
        stop=lambda: None,
        download_binary=lambda **k: None,
        start=lambda public_ip="": 1,
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.process_manager", _pm)
    monkeypatch.setattr(pkg, "process_manager", _pm, raising=False)
    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(get=lambda *a, **k: SimpleNamespace(text="b" * 40)))

    # In Debian test containers, uv exists at ~/.local/bin/uv. Disable this
    # fallback so branch expectations (git/uv missing cases) stay deterministic.
    monkeypatch.setattr("pathlib.Path.home", lambda: Path("/__nohome__"))

    # Case 1: update accepted but git missing
    monkeypatch.setattr(menu.Confirm, "ask", lambda *a, **k: True)

    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("subprocess.run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr=""))
    menu._update_screen()

    # Case 2: git exists, uv missing
    monkeypatch.setattr("shutil.which", lambda name: "git" if name == "git" else None)
    menu._update_screen()

    # Case 3: git+uv exists, pull fails
    monkeypatch.setattr("shutil.which", lambda name: "C:/bin/git" if name == "git" else "C:/bin/uv")

    def _pull_fail(cmd, **kwargs):
        if "rev-parse" in cmd:
            return SimpleNamespace(returncode=0, stdout="a" * 40, stderr="")
        if "pull" in cmd:
            return SimpleNamespace(returncode=1, stdout="", stderr="pull failed")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", _pull_fail)
    menu._update_screen()

    # Case 4: pull ok, uv sync fails
    def _sync_fail(cmd, **kwargs):
        if "rev-parse" in cmd:
            return SimpleNamespace(returncode=0, stdout="a" * 40, stderr="")
        if "pull" in cmd:
            return SimpleNamespace(returncode=0, stdout="ok", stderr="")
        if cmd and str(cmd[0]).endswith("uv"):
            return SimpleNamespace(returncode=1, stdout="", stderr="sync fail")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", _sync_fail)
    menu._update_screen()

    # Case 5: successful self-update triggers SystemExit
    _svc = SimpleNamespace(is_active=lambda name: True, restart_service=lambda name: None)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.systemd", _svc)
    monkeypatch.setattr(pkg, "systemd", _svc, raising=False)

    def _all_ok(cmd, **kwargs):
        if "rev-parse" in cmd:
            return SimpleNamespace(returncode=0, stdout="a" * 40, stderr="")
        if cmd and str(cmd[0]).endswith("uv"):
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("subprocess.run", _all_ok)
    with pytest.raises(SystemExit):
        menu._update_screen()


def test_setup_wizard_error_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _mute_ui(monkeypatch)
    import mtproxymaxpy as pkg

    binary_path = tmp_path / "telemt"
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.constants", SimpleNamespace(BINARY_PATH=binary_path))
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.network", SimpleNamespace(get_public_ip=lambda: "1.1.1.1"))

    class _Settings:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    # 1) save config failure
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(Settings=_Settings, save_settings=lambda s: (_ for _ in ()).throw(RuntimeError("save bad"))),
    )
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.secrets",
        SimpleNamespace(add_secret=lambda label: SimpleNamespace(label=label, key="a" * 32)),
    )

    prompts = iter(["1.1.1.1", "custom.domain", "TAG", "u1"])
    confirms = iter([True, True, False])
    ints = iter([443, len(menu.FAKETLS_DOMAINS)])
    monkeypatch.setattr(menu.Prompt, "ask", lambda *a, **k: next(prompts))
    monkeypatch.setattr(menu.Confirm, "ask", lambda *a, **k: next(confirms))
    monkeypatch.setattr(menu.IntPrompt, "ask", lambda *a, **k: next(ints))
    menu._setup_wizard()

    # 2) download binary fails when missing
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(Settings=_Settings, save_settings=lambda s: None),
    )
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.secrets",
        SimpleNamespace(add_secret=lambda label: SimpleNamespace(label=label, key="a" * 32)),
    )
    pm = SimpleNamespace(download_binary=lambda **k: (_ for _ in ()).throw(RuntimeError("dl bad")), start=lambda public_ip="": 1)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.process_manager", pm)
    monkeypatch.setattr(pkg, "process_manager", pm, raising=False)

    prompts = iter(["1.1.1.1", "custom.domain", "", "u1"])
    confirms = iter([True, False, False])
    ints = iter([443, len(menu.FAKETLS_DOMAINS)])
    monkeypatch.setattr(menu.Prompt, "ask", lambda *a, **k: next(prompts))
    monkeypatch.setattr(menu.Confirm, "ask", lambda *a, **k: next(confirms))
    monkeypatch.setattr(menu.IntPrompt, "ask", lambda *a, **k: next(ints))
    menu._setup_wizard()

    # 3) start fails and link generation fails, telegram setup branch true
    binary_path.write_text("ok", encoding="utf-8")
    pm2 = SimpleNamespace(download_binary=lambda **k: None, start=lambda public_ip="": (_ for _ in ()).throw(RuntimeError("start bad")))
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.process_manager", pm2)
    monkeypatch.setattr(pkg, "process_manager", pm2, raising=False)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.systemd", SimpleNamespace(install=lambda: None))
    monkeypatch.setattr(pkg, "systemd", SimpleNamespace(install=lambda: None), raising=False)
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.utils.proxy_link",
        SimpleNamespace(build_proxy_links=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("link bad"))),
    )

    called = {"tg": 0}
    monkeypatch.setattr(menu, "_telegram_setup_wizard", lambda: called.__setitem__("tg", called["tg"] + 1))

    prompts = iter(["1.1.1.1", "custom.domain", "", "u1"])
    confirms = iter([False, False, True])  # masking off, no adtag, telegram setup yes
    ints = iter([443, len(menu.FAKETLS_DOMAINS)])
    monkeypatch.setattr(menu.Prompt, "ask", lambda *a, **k: next(prompts))
    monkeypatch.setattr(menu.Confirm, "ask", lambda *a, **k: next(confirms))
    monkeypatch.setattr(menu.IntPrompt, "ask", lambda *a, **k: next(ints))
    menu._setup_wizard()
    assert called["tg"] == 1


def test_menu_secrets_and_upstreams_render_loops(monkeypatch: pytest.MonkeyPatch) -> None:
    _mute_ui(monkeypatch)
    monkeypatch.setattr(menu, "_secrets_action", lambda ch, secs: None)
    monkeypatch.setattr(menu, "_upstreams_action", lambda ch, ups: None)

    # secrets menu: one action then back, plus exception path in load_secrets
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.secrets",
        SimpleNamespace(load_secrets=lambda: [SimpleNamespace(label="u1", key="a" * 32, enabled=True, expires="", max_conns=0, notes="")]),
    )
    choices = iter([1, 0])
    monkeypatch.setattr(menu, "_ask_choice", lambda *a, **k: next(choices))
    menu._secrets_menu()

    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.secrets",
        SimpleNamespace(load_secrets=lambda: (_ for _ in ()).throw(RuntimeError("x"))),
    )
    monkeypatch.setattr(menu, "_ask_choice", lambda *a, **k: 0)
    menu._secrets_menu()

    # upstreams menu: one action then back
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.upstreams",
        SimpleNamespace(load_upstreams=lambda: [SimpleNamespace(name="u1", type="socks5", addr="1.1.1.1:1080", enabled=True, weight=10)]),
    )
    choices = iter([1, 0])
    monkeypatch.setattr(menu, "_ask_choice", lambda *a, **k: next(choices))
    menu._upstreams_menu()


def test_update_screen_engine_upgrade_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _mute_ui(monkeypatch)
    import mtproxymaxpy as pkg

    install_dir = tmp_path / "install"
    install_dir.mkdir()
    sha_file = tmp_path / "sha"
    badge_file = tmp_path / "badge"

    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.constants",
        SimpleNamespace(
            GITHUB_REPO="owner/repo",
            GITHUB_API_COMMITS="https://api.example/commits",
            INSTALL_DIR=install_dir,
            UPDATE_SHA_FILE=sha_file,
            UPDATE_BADGE_FILE=badge_file,
            VERSION="1.0.0",
            TELEMT_VERSION="1.0.0",
            SYSTEMD_TELEGRAM_SERVICE="mtproxymaxpy-telegram",
        ),
    )

    # keep self-update in no-op state so engine block runs
    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(get=lambda *a, **k: SimpleNamespace(text="a" * 40)))
    monkeypatch.setattr("subprocess.run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="a" * 40, stderr=""))

    calls = {"stop": 0, "dl": 0, "start": 0}
    pm = SimpleNamespace(
        get_latest_version=lambda: "2.0.0",
        is_running=lambda: True,
        stop=lambda: calls.__setitem__("stop", calls["stop"] + 1),
        download_binary=lambda **k: calls.__setitem__("dl", calls["dl"] + 1),
        start=lambda public_ip="": calls.__setitem__("start", calls["start"] + 1) or 123,
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.process_manager", pm)
    monkeypatch.setattr(pkg, "process_manager", pm, raising=False)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.network", SimpleNamespace(get_public_ip=lambda: "1.2.3.4"))

    confirms = iter([True])  # self-update prompt is skipped in up-to-date branch; engine prompt only
    monkeypatch.setattr(menu.Confirm, "ask", lambda *a, **k: next(confirms))
    menu._update_screen()
    assert calls == {"stop": 1, "dl": 1, "start": 1}


def test_update_screen_engine_upgrade_is_not_reoffered_after_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _mute_ui(monkeypatch)
    import mtproxymaxpy as pkg

    install_dir = tmp_path / "install"
    install_dir.mkdir()
    sha_file = tmp_path / "sha"
    badge_file = tmp_path / "badge"

    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.constants",
        SimpleNamespace(
            GITHUB_REPO="owner/repo",
            GITHUB_API_COMMITS="https://api.example/commits",
            INSTALL_DIR=install_dir,
            UPDATE_SHA_FILE=sha_file,
            UPDATE_BADGE_FILE=badge_file,
            VERSION="1.0.0",
            TELEMT_VERSION="3.3.39",
            SYSTEMD_TELEGRAM_SERVICE="mtproxymaxpy-telegram",
        ),
    )

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(get=lambda *a, **k: SimpleNamespace(text="a" * 40)))
    monkeypatch.setattr("subprocess.run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="a" * 40, stderr=""))

    state = {"installed": "3.3.39"}
    calls = {"stop": 0, "dl": 0, "start": 0}

    def _download_binary(**kwargs):
        calls["dl"] += 1
        state["installed"] = kwargs["version"]

    pm = SimpleNamespace(
        get_latest_version=lambda: "3.4.0",
        get_binary_version=lambda: state["installed"],
        is_running=lambda: True,
        stop=lambda: calls.__setitem__("stop", calls["stop"] + 1),
        download_binary=_download_binary,
        start=lambda public_ip="": calls.__setitem__("start", calls["start"] + 1) or 123,
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.process_manager", pm)
    monkeypatch.setattr(pkg, "process_manager", pm, raising=False)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.network", SimpleNamespace(get_public_ip=lambda: "1.2.3.4"))

    confirms = iter([True, True])
    monkeypatch.setattr(menu.Confirm, "ask", lambda *a, **k: next(confirms, False))

    menu._update_screen()
    menu._update_screen()

    assert calls == {"stop": 1, "dl": 1, "start": 1}


def test_menu_loop_exception_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    _mute_ui(monkeypatch)

    # _secrets_menu KeyboardInterrupt branch
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.secrets",
        SimpleNamespace(load_secrets=lambda: [SimpleNamespace(label="u1", key="a" * 32, enabled=True, expires="", max_conns=0, notes="")]),
    )
    monkeypatch.setattr(menu, "_ask_choice", lambda *a, **k: 1)
    monkeypatch.setattr(menu, "_secrets_action", lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
    menu._secrets_menu()

    # _secrets_menu generic exception branch
    paused = {"n": 0}
    monkeypatch.setattr(menu, "_pause", lambda: paused.__setitem__("n", paused["n"] + 1))
    seq = iter([1, 0])
    monkeypatch.setattr(menu, "_ask_choice", lambda *a, **k: next(seq))
    monkeypatch.setattr(menu, "_secrets_action", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    menu._secrets_menu()
    assert paused["n"] >= 1

    # _upstreams_menu generic exception branch
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.upstreams",
        SimpleNamespace(load_upstreams=lambda: [SimpleNamespace(name="u1", type="socks5", addr="1.1.1.1:1080", enabled=True, weight=10)]),
    )
    paused2 = {"n": 0}
    monkeypatch.setattr(menu, "_pause", lambda: paused2.__setitem__("n", paused2["n"] + 1))
    seq2 = iter([1, 0])
    monkeypatch.setattr(menu, "_ask_choice", lambda *a, **k: next(seq2))
    monkeypatch.setattr(menu, "_upstreams_action", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    menu._upstreams_menu()
    assert paused2["n"] >= 1
