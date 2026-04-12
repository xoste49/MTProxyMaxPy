from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace

import pytest


def _import_tui_modules():
    class _W:
        def __init__(self, *a, **k):
            self.id = k.get("id")
            self.value = k.get("value", "")
            self.label = k.get("label", "")
            self.variant = k.get("variant", "")
            self.disabled = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Button(_W):
        class Pressed:
            def __init__(self, button):
                self.button = button

    class _DataTable(_W):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.cursor_row = 0

    class _Switch(_W):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.value = k.get("value", False)

    class _Select(_W):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.value = k.get("value", "")

    class _Reactive:
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, default):
            self.default = default

    sys.modules.setdefault("textual", SimpleNamespace())
    sys.modules["textual.app"] = SimpleNamespace(ComposeResult=object)
    sys.modules["textual.screen"] = SimpleNamespace(Screen=_W)
    sys.modules["textual.widgets"] = SimpleNamespace(
        Button=_Button,
        Footer=_W,
        Header=_W,
        Label=_W,
        Log=_W,
        Checkbox=_W,
        DataTable=_DataTable,
        Input=_W,
        Switch=_Switch,
        Select=_Select,
        Sparkline=_W,
        Static=_W,
    )
    sys.modules["textual.containers"] = SimpleNamespace(
        Center=_W,
        Vertical=_W,
        Horizontal=_W,
        ScrollableContainer=_W,
    )
    sys.modules["textual.reactive"] = SimpleNamespace(reactive=_Reactive)

    return {
        "main_menu": importlib.import_module("mtproxymaxpy.tui.screens.main_menu"),
        "migration_screen": importlib.import_module("mtproxymaxpy.tui.screens.migration_screen"),
        "secrets_screen": importlib.import_module("mtproxymaxpy.tui.screens.secrets_screen"),
        "settings_screen": importlib.import_module("mtproxymaxpy.tui.screens.settings_screen"),
        "status_screen": importlib.import_module("mtproxymaxpy.tui.screens.status_screen"),
        "upstreams_screen": importlib.import_module("mtproxymaxpy.tui.screens.upstreams_screen"),
        "proxy_link": importlib.import_module("mtproxymaxpy.tui.widgets.proxy_link"),
        "status_box": importlib.import_module("mtproxymaxpy.tui.widgets.status_box"),
        "traffic_chart": importlib.import_module("mtproxymaxpy.tui.widgets.traffic_chart"),
    }


class _DummyApp:
    def __init__(self):
        self.actions = []

    def push_screen(self, name):
        self.actions.append(("push", name))

    def pop_screen(self):
        self.actions.append(("pop", None))

    def exit(self):
        self.actions.append(("exit", None))

    def bell(self):
        self.actions.append(("bell", None))


def test_proxy_link_helpers_and_widget_compose(monkeypatch: pytest.MonkeyPatch) -> None:
    mods = _import_tui_modules()
    proxy_link = mods["proxy_link"]

    url = proxy_link._build_link("1.2.3.4", 443, "a" * 32, "cloudflare.com")
    assert "server=1.2.3.4" in url
    assert "domain=cloudflare.com" in url

    class _QR:
        def __init__(self, border=1):
            self.data = None

        def add_data(self, d):
            self.data = d

        def make(self, fit=True):
            return None

        def print_ascii(self, out=None, invert=True):
            out.write("QR\n")

    monkeypatch.setitem(sys.modules, "qrcode", SimpleNamespace(QRCode=_QR))
    assert "QR" in proxy_link._qr_text("hello")

    w = proxy_link.ProxyLink("1.2.3.4", 443, "a" * 32, "cloudflare.com", label="L")
    nodes = list(w.compose())
    assert len(nodes) == 3


def test_status_box_render_and_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    mods = _import_tui_modules()
    status_box = mods["status_box"]

    sb = status_box.StatusBox(label="node")
    sb.running = False
    assert "STOPPED" in sb.render()
    sb.running = True
    assert "RUNNING" in sb.render()

    import mtproxymaxpy as pkg

    pm = SimpleNamespace(is_running=lambda: True)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.process_manager", pm)
    monkeypatch.setattr(pkg, "process_manager", pm, raising=False)
    sb.refresh_status()
    assert sb.running is True


def test_traffic_chart_helpers(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    mods = _import_tui_modules()
    traffic_chart = mods["traffic_chart"]

    stats_dir = tmp_path / "stats"
    stats_dir.mkdir()
    (stats_dir / "a.txt").write_text("1.5", encoding="utf-8")
    (stats_dir / "b.txt").write_text("bad", encoding="utf-8")
    monkeypatch.setattr(traffic_chart, "STATS_DIR", stats_dir)
    vals = traffic_chart._read_stats()
    assert vals == [1.5, 0.0]

    fake_spark = SimpleNamespace(data=[])
    fake_self = SimpleNamespace(query_one=lambda selector, cls=None: fake_spark)
    traffic_chart.TrafficChart.refresh_data(fake_self)
    assert fake_spark.data == [1.5, 0.0]


def test_main_menu_buttons_and_proxy_action(monkeypatch: pytest.MonkeyPatch) -> None:
    mods = _import_tui_modules()
    MainMenuScreen = mods["main_menu"].MainMenuScreen

    app = _DummyApp()
    refreshed = {"n": 0}
    fake_status_box = SimpleNamespace(refresh_status=lambda: refreshed.__setitem__("n", refreshed["n"] + 1))

    class _FakeSelf:
        def __init__(self):
            self.app = app
            self.notified = []

        def query_one(self, cls):
            return fake_status_box

        def notify(self, text, severity=None):
            self.notified.append((text, severity))

    fake = _FakeSelf()
    for btn, expected in (
        ("btn-status", ("push", "status")),
        ("btn-secrets", ("push", "secrets")),
        ("btn-upstreams", ("push", "upstreams")),
        ("btn-settings", ("push", "settings")),
        ("btn-quit", ("exit", None)),
    ):
        MainMenuScreen.on_button_pressed(fake, SimpleNamespace(button=SimpleNamespace(id=btn)))
        assert app.actions[-1] == expected

    called = []
    pm = SimpleNamespace(
        start=lambda public_ip="": called.append("start"),
        stop=lambda: called.append("stop"),
        restart=lambda public_ip="": called.append("restart"),
    )
    import mtproxymaxpy as pkg

    monkeypatch.setitem(sys.modules, "mtproxymaxpy.process_manager", pm)
    monkeypatch.setattr(pkg, "process_manager", pm, raising=False)
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.network", SimpleNamespace(get_public_ip=lambda: "1.1.1.1"))
    MainMenuScreen._proxy_action(fake, "start")
    MainMenuScreen._proxy_action(fake, "stop")
    MainMenuScreen._proxy_action(fake, "restart")
    assert called == ["start", "stop", "restart"]
    assert refreshed["n"] == 3

    pm2 = SimpleNamespace(start=lambda public_ip="": (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.process_manager", pm2)
    monkeypatch.setattr(pkg, "process_manager", pm2, raising=False)
    MainMenuScreen._proxy_action(fake, "start")
    assert app.actions[-1] == ("bell", None)
    assert fake.notified[-1][1] == "error"


def test_migration_screen_button_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    mods = _import_tui_modules()
    MigrationScreen = mods["migration_screen"].MigrationScreen

    files = {"settings": object()}
    screen = MigrationScreen(files)
    screen.app = _DummyApp()

    logs = []
    import_btn = SimpleNamespace(disabled=False)
    skip_btn = SimpleNamespace(label="Skip", variant="default")
    checkbox = SimpleNamespace(value=True)
    log_widget = SimpleNamespace(write_line=lambda line: logs.append(line))

    def _q(selector, cls=None):
        return {
            "#chk-settings": checkbox,
            "#migration-log": log_widget,
            "#btn-import": import_btn,
            "#btn-skip": skip_btn,
        }[selector]

    notices = []
    screen.query_one = _q
    screen.notify = lambda text, severity=None: notices.append((text, severity))

    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.migration",
        SimpleNamespace(
            run_migration=lambda files: SimpleNamespace(
                settings_imported=True, secrets_count=1, upstreams_count=2, instances_count=3, errors=[]
            )
        ),
    )

    MigrationScreen.on_button_pressed(screen, SimpleNamespace(button=SimpleNamespace(id="btn-import")))
    assert any("imported" in x for x in logs)
    assert import_btn.disabled is True
    assert skip_btn.variant == "success"

    checkbox.value = False
    MigrationScreen.on_button_pressed(screen, SimpleNamespace(button=SimpleNamespace(id="btn-import")))
    assert notices[-1][1] == "warning"

    MigrationScreen.on_button_pressed(screen, SimpleNamespace(button=SimpleNamespace(id="btn-skip")))
    assert screen.app.actions[-1] == ("pop", None)


def test_screen_compose_methods(monkeypatch: pytest.MonkeyPatch) -> None:
    mods = _import_tui_modules()
    MainMenuScreen = mods["main_menu"].MainMenuScreen
    MigrationScreen = mods["migration_screen"].MigrationScreen
    SecretsScreen = mods["secrets_screen"].SecretsScreen
    SettingsScreen = mods["settings_screen"].SettingsScreen
    StatusScreen = mods["status_screen"].StatusScreen
    UpstreamsScreen = mods["upstreams_screen"].UpstreamsScreen

    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(
            load_settings=lambda: SimpleNamespace(
                proxy_port=443,
                proxy_domain="cf.com",
                proxy_concurrency=1000,
                custom_ip="",
                masking_enabled=True,
                masking_host="",
                telegram_enabled=False,
                telegram_bot_token="",
                telegram_chat_id="",
                telegram_server_label="srv",
            )
        ),
    )

    assert list(MainMenuScreen().compose())
    assert list(MigrationScreen({"settings": object()}).compose())
    assert list(SecretsScreen().compose())
    assert list(SettingsScreen().compose())
    assert list(StatusScreen().compose())
    assert list(UpstreamsScreen().compose())


def test_secrets_screen_reload_and_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    mods = _import_tui_modules()
    SecretsScreen = mods["secrets_screen"].SecretsScreen

    table_rows = []
    table = SimpleNamespace(
        cursor_row=0,
        add_columns=lambda *a: None,
        clear=lambda: table_rows.clear(),
        add_row=lambda *a, **k: table_rows.append(a),
        get_row_at=lambda idx: table_rows[idx],
    )
    inp = SimpleNamespace(value="new-label")
    app = _DummyApp()

    class _Self:
        def __init__(self):
            self.app = app
            self.notes = []

        def query_one(self, selector, cls=None):
            if selector == "#new-label":
                return inp
            return table

        def notify(self, text, severity=None):
            self.notes.append((text, severity))

    fake = _Self()
    fake._reload_table = lambda: SecretsScreen._reload_table(fake)
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.secrets",
        SimpleNamespace(
            load_secrets=lambda: [SimpleNamespace(label="a", key="a" * 32, enabled=True, expires="", notes="n")],
            add_secret=lambda label: None,
            remove_secret=lambda label: True,
            rotate_secret=lambda label: SimpleNamespace(key="b" * 32),
        ),
    )

    SecretsScreen.on_mount(fake)
    assert table_rows
    SecretsScreen.on_button_pressed(fake, SimpleNamespace(button=SimpleNamespace(id="btn-add")))
    assert inp.value == ""
    SecretsScreen.on_button_pressed(fake, SimpleNamespace(button=SimpleNamespace(id="btn-remove")))
    SecretsScreen.on_button_pressed(fake, SimpleNamespace(button=SimpleNamespace(id="btn-rotate")))

    inp.value = ""
    SecretsScreen.on_button_pressed(fake, SimpleNamespace(button=SimpleNamespace(id="btn-add")))
    assert fake.notes[-1][1] == "warning"

    table.cursor_row = None
    SecretsScreen.on_button_pressed(fake, SimpleNamespace(button=SimpleNamespace(id="btn-remove")))
    assert fake.notes[-1][1] == "warning"

    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.secrets",
        SimpleNamespace(
            load_secrets=lambda: [SimpleNamespace(label="a", key="a" * 32, enabled=True, expires="", notes="n")],
            add_secret=lambda label: (_ for _ in ()).throw(ValueError("bad")),
            remove_secret=lambda label: True,
            rotate_secret=lambda label: (_ for _ in ()).throw(KeyError("no")),
        ),
    )
    table.cursor_row = 0
    inp.value = "x"
    SecretsScreen.on_button_pressed(fake, SimpleNamespace(button=SimpleNamespace(id="btn-add")))
    SecretsScreen.on_button_pressed(fake, SimpleNamespace(button=SimpleNamespace(id="btn-rotate")))
    assert fake.notes[-1][1] == "error"

    SecretsScreen.on_button_pressed(fake, SimpleNamespace(button=SimpleNamespace(id="btn-back")))
    assert app.actions[-1] == ("pop", None)


def test_settings_screen_save_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    mods = _import_tui_modules()
    SettingsScreen = mods["settings_screen"].SettingsScreen

    saved = []

    class _Settings:
        def __init__(self, **kw):
            self.kw = kw

    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.settings",
        SimpleNamespace(
            Settings=_Settings,
            save_settings=lambda s: saved.append(s),
            load_settings=lambda: SimpleNamespace(
                proxy_port=443,
                proxy_domain="cf.com",
                proxy_concurrency=1000,
                custom_ip="",
                masking_enabled=True,
                masking_host="",
                telegram_enabled=False,
                telegram_bot_token="",
                telegram_chat_id="",
                telegram_server_label="srv",
            ),
        ),
    )

    inputs = {
        "#port": SimpleNamespace(value="443"),
        "#domain": SimpleNamespace(value="cloudflare.com"),
        "#concurrency": SimpleNamespace(value="1000"),
        "#custom-ip": SimpleNamespace(value=""),
        "#masking-host": SimpleNamespace(value=""),
        "#tg-token": SimpleNamespace(value=""),
        "#tg-chat-id": SimpleNamespace(value=""),
        "#tg-label": SimpleNamespace(value="node"),
        "#masking-enabled": SimpleNamespace(value=True),
        "#tg-enabled": SimpleNamespace(value=False),
    }

    class _Self:
        def __init__(self):
            self.app = _DummyApp()
            self.notices = []

        def query_one(self, selector, cls=None):
            return inputs[selector]

        def notify(self, text, severity=None):
            self.notices.append((text, severity))

    fake = _Self()
    fake._save = lambda: SettingsScreen._save(fake)
    SettingsScreen._save(fake)
    assert saved and saved[-1].kw["proxy_port"] == 443

    inputs["#port"].value = "bad"
    SettingsScreen._save(fake)
    assert fake.notices[-1][1] == "error"

    SettingsScreen.on_button_pressed(fake, SimpleNamespace(button=SimpleNamespace(id="btn-back")))
    assert fake.app.actions[-1] == ("pop", None)


def test_status_screen_refresh_and_back(monkeypatch: pytest.MonkeyPatch) -> None:
    mods = _import_tui_modules()
    StatusScreen = mods["status_screen"].StatusScreen
    status_box = mods["status_box"]
    traffic_chart = mods["traffic_chart"]

    sb = SimpleNamespace(refresh_status=lambda: None)
    details = SimpleNamespace(update=lambda text: setattr(details, "text", text))
    tc = SimpleNamespace(refresh_data=lambda: None)
    mounted = []
    links = SimpleNamespace(remove_children=lambda: mounted.clear(), mount=lambda x: mounted.append(x))
    app = _DummyApp()

    class _Self:
        def __init__(self):
            self.app = app

        def query_one(self, selector, cls=None):
            mapping = {
                status_box.StatusBox: sb,
                "#details": details,
                traffic_chart.TrafficChart: tc,
                "#links": links,
            }
            return mapping[selector]

    fake = _Self()
    _set = SimpleNamespace(proxy_port=443, proxy_concurrency=1000, custom_ip="", proxy_domain="cf.com")
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.process_manager", SimpleNamespace(status=lambda: {"pid": 1}))
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.config.settings", SimpleNamespace(load_settings=lambda: _set))
    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.secrets",
        SimpleNamespace(load_secrets=lambda: [SimpleNamespace(enabled=True, key="a" * 32, label="u")]),
    )
    monkeypatch.setitem(sys.modules, "mtproxymaxpy.utils.network", SimpleNamespace(get_public_ip=lambda: "1.1.1.1"))

    StatusScreen._refresh_all(fake)
    assert "Port:" in details.text
    assert len(mounted) == 1

    fake._refresh_all = lambda: StatusScreen._refresh_all(fake)
    StatusScreen.on_mount(fake)
    StatusScreen.action_refresh(fake)

    StatusScreen.on_button_pressed(fake, SimpleNamespace(button=SimpleNamespace(id="btn-back")))
    assert app.actions[-1] == ("pop", None)


def test_upstreams_screen_reload_and_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    mods = _import_tui_modules()
    UpstreamsScreen = mods["upstreams_screen"].UpstreamsScreen

    rows = []
    table = SimpleNamespace(
        cursor_row=0,
        add_columns=lambda *a: None,
        clear=lambda: rows.clear(),
        add_row=lambda *a, **k: rows.append(a),
        get_row_at=lambda idx: rows[idx],
    )
    inputs = {
        "#inp-name": SimpleNamespace(value="u1"),
        "#inp-addr": SimpleNamespace(value="1.1.1.1:1080"),
        "#sel-type": SimpleNamespace(value="socks5"),
    }

    class _Self:
        def __init__(self):
            self.app = _DummyApp()
            self.notes = []

        def query_one(self, selector, cls=None):
            if selector == table.__class__:
                return table
            if selector in inputs:
                return inputs[selector]
            return table

        def notify(self, text, severity=None):
            self.notes.append((text, severity))

    fake = _Self()
    fake._reload_table = lambda: UpstreamsScreen._reload_table(fake)
    items = [SimpleNamespace(name="u0", type="socks5", addr="1", weight=10, enabled=True)]

    class _Up:
        def __init__(self, name, type, addr):
            self.name = name
            self.type = type
            self.addr = addr
            self.weight = 10
            self.enabled = True

    monkeypatch.setitem(
        sys.modules,
        "mtproxymaxpy.config.upstreams",
        SimpleNamespace(
            load_upstreams=lambda: items,
            save_upstreams=lambda new: items.__setitem__(slice(None), list(new)),
            Upstream=_Up,
        ),
    )

    UpstreamsScreen.on_mount(fake)
    assert rows

    UpstreamsScreen.on_button_pressed(fake, SimpleNamespace(button=SimpleNamespace(id="btn-add")))
    assert any(u.name == "u1" for u in items)

    UpstreamsScreen.on_button_pressed(fake, SimpleNamespace(button=SimpleNamespace(id="btn-remove")))
    assert not any(u.name == "u0" for u in items)

    inputs["#inp-name"].value = ""
    UpstreamsScreen.on_button_pressed(fake, SimpleNamespace(button=SimpleNamespace(id="btn-add")))
    assert fake.notes[-1][1] == "warning"

    inputs["#inp-name"].value = "u1"
    UpstreamsScreen.on_button_pressed(fake, SimpleNamespace(button=SimpleNamespace(id="btn-add")))
    assert fake.notes[-1][1] == "error"

    UpstreamsScreen.on_button_pressed(fake, SimpleNamespace(button=SimpleNamespace(id="btn-back")))
    assert fake.app.actions[-1] == ("pop", None)
