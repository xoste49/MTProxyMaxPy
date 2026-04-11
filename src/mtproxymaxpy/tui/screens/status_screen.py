"""Status screen — live proxy info, traffic chart, and proxy links."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Label
from textual.containers import Vertical, ScrollableContainer

from mtproxymaxpy.tui.widgets.status_box import StatusBox
from mtproxymaxpy.tui.widgets.traffic_chart import TrafficChart
from mtproxymaxpy.tui.widgets.proxy_link import ProxyLink
from mtproxymaxpy.utils.formatting import format_bytes


class StatusScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back"), ("r", "refresh", "Refresh")]

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer():
            yield StatusBox(id="status-box")
            yield Label("", id="details")
            yield TrafficChart(id="traffic")
            yield Vertical(id="links")
        yield Button("← Back", id="btn-back")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_all()

    def action_refresh(self) -> None:
        self._refresh_all()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()

    def _refresh_all(self) -> None:
        from mtproxymaxpy import process_manager
        from mtproxymaxpy.config.settings import load_settings
        from mtproxymaxpy.config.secrets import load_secrets
        from mtproxymaxpy.utils.network import get_public_ip

        sb = self.query_one(StatusBox)
        sb.refresh_status()

        st = process_manager.status()
        settings = load_settings()
        secrets = load_secrets()
        ip = get_public_ip() or settings.custom_ip or "?"

        details = self.query_one("#details", Label)
        details.update(
            f"Port: [bold]{settings.proxy_port}[/bold]  "
            f"IP: [bold]{ip}[/bold]  "
            f"PID: [bold]{st['pid'] or 'N/A'}[/bold]  "
            f"Concurrency: [bold]{settings.proxy_concurrency}[/bold]"
        )

        self.query_one(TrafficChart).refresh_data()

        # Re-render proxy links
        links_container = self.query_one("#links", Vertical)
        links_container.remove_children()
        for s in secrets:
            if s.enabled:
                links_container.mount(
                    ProxyLink(ip, settings.proxy_port, s.key,
                              settings.proxy_domain, label=s.label)
                )
