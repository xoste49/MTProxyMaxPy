"""Main menu screen."""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label
from textual.containers import Center, Vertical

from mtproxymaxpy.constants import APP_TITLE, VERSION
from mtproxymaxpy.tui.widgets.status_box import StatusBox


class MainMenuScreen(Screen):
    BINDINGS = [("q", "app.quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Center():
            with Vertical(id="menu"):
                yield StatusBox(id="status-box")
                yield Label("")
                yield Button("📊  Status",        id="btn-status",   variant="default")
                yield Button("🔑  Secrets",       id="btn-secrets",  variant="default")
                yield Button("🌐  Upstreams",     id="btn-upstreams",variant="default")
                yield Button("⚙️   Settings",      id="btn-settings", variant="default")
                yield Label("")
                yield Button("▶   Start",         id="btn-start",    variant="success")
                yield Button("■   Stop",          id="btn-stop",     variant="error")
                yield Button("↺   Restart",       id="btn-restart",  variant="warning")
                yield Label("")
                yield Button("✕   Quit",          id="btn-quit",     variant="default")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(StatusBox).refresh_status()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-status":
            self.app.push_screen("status")
        elif btn_id == "btn-secrets":
            self.app.push_screen("secrets")
        elif btn_id == "btn-upstreams":
            self.app.push_screen("upstreams")
        elif btn_id == "btn-settings":
            self.app.push_screen("settings")
        elif btn_id == "btn-start":
            self._proxy_action("start")
        elif btn_id == "btn-stop":
            self._proxy_action("stop")
        elif btn_id == "btn-restart":
            self._proxy_action("restart")
        elif btn_id == "btn-quit":
            self.app.exit()

    def _proxy_action(self, action: str) -> None:
        from mtproxymaxpy import process_manager
        from mtproxymaxpy.utils.network import get_public_ip

        try:
            if action == "start":
                process_manager.start(public_ip=get_public_ip() or "")
            elif action == "stop":
                process_manager.stop()
            elif action == "restart":
                process_manager.restart(public_ip=get_public_ip() or "")
        except Exception as exc:
            self.app.bell()
            self.notify(str(exc), severity="error")
        finally:
            self.query_one(StatusBox).refresh_status()
