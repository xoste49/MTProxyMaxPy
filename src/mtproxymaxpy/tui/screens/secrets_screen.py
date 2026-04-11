"""Secrets management screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label
from textual.containers import Horizontal, Vertical


class SecretsScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="secrets-table", cursor_type="row")
        with Horizontal(id="toolbar"):
            yield Input(placeholder="Label for new secret", id="new-label")
            yield Button("Add", id="btn-add", variant="success")
            yield Button("Remove", id="btn-remove", variant="error")
            yield Button("Rotate key", id="btn-rotate", variant="warning")
        yield Button("← Back", id="btn-back")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Label", "Key (first 8)", "Enabled", "Expires", "Notes")
        self._reload_table()

    def _reload_table(self) -> None:
        from mtproxymaxpy.config.secrets import load_secrets

        table = self.query_one(DataTable)
        table.clear()
        for s in load_secrets():
            table.add_row(
                s.label,
                s.key[:8] + "…",
                "✓" if s.enabled else "✗",
                s.expires or "never",
                s.notes,
                key=s.label,
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
            return

        table = self.query_one(DataTable)

        if event.button.id == "btn-add":
            label = self.query_one("#new-label", Input).value.strip()
            if not label:
                self.notify("Enter a label first.", severity="warning")
                return
            from mtproxymaxpy.config.secrets import add_secret
            try:
                add_secret(label)
                self.query_one("#new-label", Input).value = ""
                self._reload_table()
                self.notify(f"Secret '{label}' added.", severity="information")
            except ValueError as exc:
                self.notify(str(exc), severity="error")

        elif event.button.id in ("btn-remove", "btn-rotate"):
            row_key = table.cursor_row
            if row_key is None:
                self.notify("Select a row first.", severity="warning")
                return
            # Get label from first cell of selected row
            row = table.get_row_at(table.cursor_row)
            label = str(row[0])

            if event.button.id == "btn-remove":
                from mtproxymaxpy.config.secrets import remove_secret
                remove_secret(label)
                self._reload_table()
                self.notify(f"Secret '{label}' removed.")
            else:
                from mtproxymaxpy.config.secrets import rotate_secret
                try:
                    s = rotate_secret(label)
                    self._reload_table()
                    self.notify(f"New key for '{label}': {s.key[:8]}…")
                except KeyError as exc:
                    self.notify(str(exc), severity="error")
