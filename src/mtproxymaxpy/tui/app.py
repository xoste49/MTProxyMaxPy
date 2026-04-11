"""MTProxyMaxPy Textual application."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

from mtproxymaxpy.constants import APP_TITLE, VERSION
from mtproxymaxpy.tui.screens.main_menu import MainMenuScreen
from mtproxymaxpy.tui.screens.status_screen import StatusScreen
from mtproxymaxpy.tui.screens.secrets_screen import SecretsScreen
from mtproxymaxpy.tui.screens.upstreams_screen import UpstreamsScreen
from mtproxymaxpy.tui.screens.settings_screen import SettingsScreen


_CSS = """
Screen {
    align: center middle;
}
#menu {
    width: 50;
    height: auto;
    padding: 1 2;
    border: double $accent;
}
#menu Button {
    width: 100%;
    margin: 0 0 1 0;
}
.lbl {
    width: 18;
    padding: 1 0 0 1;
}
#toolbar {
    height: auto;
    padding: 1 0;
}
#toolbar Input, #toolbar Select {
    width: 1fr;
}
"""


class MTProxyMaxPyApp(App):
    TITLE = f"{APP_TITLE} v{VERSION}"
    CSS = _CSS
    SCREENS = {
        "main": MainMenuScreen,
        "status": StatusScreen,
        "secrets": SecretsScreen,
        "upstreams": UpstreamsScreen,
        "settings": SettingsScreen,
    }
    BINDINGS = [("ctrl+c", "quit", "Quit")]

    async def on_mount(self) -> None:
        # Check for legacy configs before showing main menu
        from mtproxymaxpy.config.migration import detect_legacy
        from mtproxymaxpy.constants import SETTINGS_FILE

        legacy = detect_legacy()
        if legacy and not SETTINGS_FILE.exists():
            from mtproxymaxpy.tui.screens.migration_screen import MigrationScreen
            await self.push_screen(MigrationScreen(legacy))
        else:
            await self.push_screen(MainMenuScreen())


def run_tui() -> None:
    """Launch the Textual TUI application."""
    MTProxyMaxPyApp().run()
