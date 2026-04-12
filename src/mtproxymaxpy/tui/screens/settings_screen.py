"""Settings screen — edit global proxy settings."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Switch
from textual.containers import Horizontal, ScrollableContainer, Vertical


class SettingsScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        from mtproxymaxpy.config.settings import load_settings

        s = load_settings()
        yield Header()
        with ScrollableContainer():
            yield Label("[bold]Proxy[/bold]")
            with Horizontal():
                yield Label("Port: ", classes="lbl")
                yield Input(str(s.proxy_port), id="port")
            with Horizontal():
                yield Label("Domain: ", classes="lbl")
                yield Input(s.proxy_domain, id="domain")
            with Horizontal():
                yield Label("Concurrency: ", classes="lbl")
                yield Input(str(s.proxy_concurrency), id="concurrency")
            with Horizontal():
                yield Label("Custom IP: ", classes="lbl")
                yield Input(s.custom_ip, id="custom-ip")
            yield Label("[bold]Masking[/bold]")
            with Horizontal():
                yield Label("Enabled: ", classes="lbl")
                yield Switch(value=s.masking_enabled, id="masking-enabled")
            with Horizontal():
                yield Label("Masking host: ", classes="lbl")
                yield Input(s.masking_host, id="masking-host")
            yield Label("[bold]Telegram Bot[/bold]")
            with Horizontal():
                yield Label("Enabled: ", classes="lbl")
                yield Switch(value=s.telegram_enabled, id="tg-enabled")
            with Horizontal():
                yield Label("Token: ", classes="lbl")
                yield Input(s.telegram_bot_token, password=True, id="tg-token")
            with Horizontal():
                yield Label("Chat ID: ", classes="lbl")
                yield Input(s.telegram_chat_id, id="tg-chat-id")
            with Horizontal():
                yield Label("Server label: ", classes="lbl")
                yield Input(s.telegram_server_label, id="tg-label")
        with Horizontal():
            yield Button("Save", id="btn-save", variant="success")
            yield Button("← Back", id="btn-back")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
        elif event.button.id == "btn-save":
            self._save()

    def _save(self) -> None:
        from mtproxymaxpy.config.settings import Settings, save_settings

        def ival(id_: str) -> str:
            return self.query_one(f"#{id_}", Input).value.strip()

        def sval(id_: str) -> bool:
            return self.query_one(f"#{id_}", Switch).value

        try:
            settings = Settings(
                proxy_port=int(ival("port")),
                proxy_domain=ival("domain"),
                proxy_concurrency=int(ival("concurrency")),
                custom_ip=ival("custom-ip"),
                masking_enabled=sval("masking-enabled"),
                masking_host=ival("masking-host"),
                telegram_enabled=sval("tg-enabled"),
                telegram_bot_token=ival("tg-token"),
                telegram_chat_id=ival("tg-chat-id"),
                telegram_server_label=ival("tg-label"),
            )
            save_settings(settings)
            self.notify("Settings saved.", severity="information")
        except Exception as exc:
            self.notify(str(exc), severity="error")
