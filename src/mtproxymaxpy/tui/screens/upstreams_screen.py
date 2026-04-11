"""Upstreams management screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Select
from textual.containers import Horizontal


class UpstreamsScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="upstreams-table", cursor_type="row")
        with Horizontal(id="toolbar"):
            yield Input(placeholder="Name", id="inp-name")
            yield Select(
                [("direct", "direct"), ("socks5", "socks5"), ("socks4", "socks4")],
                value="socks5",
                id="sel-type",
            )
            yield Input(placeholder="host:port", id="inp-addr")
            yield Button("Add", id="btn-add", variant="success")
            yield Button("Remove", id="btn-remove", variant="error")
        yield Button("← Back", id="btn-back")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Name", "Type", "Address", "Weight", "Enabled")
        self._reload_table()

    def _reload_table(self) -> None:
        from mtproxymaxpy.config.upstreams import load_upstreams

        table = self.query_one(DataTable)
        table.clear()
        for u in load_upstreams():
            table.add_row(
                u.name,
                u.type,
                u.addr,
                str(u.weight),
                "✓" if u.enabled else "✗",
                key=u.name,
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
            return

        if event.button.id == "btn-add":
            name = self.query_one("#inp-name", Input).value.strip()
            addr = self.query_one("#inp-addr", Input).value.strip()
            utype = self.query_one("#sel-type", Select).value or "socks5"
            if not name:
                self.notify("Name is required.", severity="warning")
                return
            from mtproxymaxpy.config.upstreams import Upstream, load_upstreams, save_upstreams
            items = load_upstreams()
            if any(u.name == name for u in items):
                self.notify(f"'{name}' already exists.", severity="error")
                return
            items.append(Upstream(name=name, type=utype, addr=addr))  # type: ignore[arg-type]
            save_upstreams(items)
            self._reload_table()
            self.notify(f"Upstream '{name}' added.")

        elif event.button.id == "btn-remove":
            table = self.query_one(DataTable)
            row = table.get_row_at(table.cursor_row)
            name = str(row[0])
            from mtproxymaxpy.config.upstreams import load_upstreams, save_upstreams
            items = [u for u in load_upstreams() if u.name != name]
            save_upstreams(items)
            self._reload_table()
            self.notify(f"Upstream '{name}' removed.")
