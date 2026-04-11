"""Migration screen — shown on first launch when legacy bash configs are found."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Footer, Header, Label, Log
from textual.containers import Vertical, Horizontal


class MigrationScreen(Screen):
    """Offers to import legacy bash-format config files."""

    def __init__(self, legacy_files: dict[str, Path], **kwargs) -> None:
        super().__init__(**kwargs)
        self._files = legacy_files

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label(
            "[bold yellow]Legacy configuration detected![/bold yellow]\n"
            "The following bash-format config files were found:"
        )
        with Vertical(id="checks"):
            for key, path in self._files.items():
                yield Checkbox(f"{key}  ({path})", value=True, id=f"chk-{key}")
        yield Log(id="migration-log", highlight=True)
        with Horizontal():
            yield Button("Import selected", id="btn-import", variant="success")
            yield Button("Skip (start fresh)", id="btn-skip", variant="default")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-skip":
            self.app.pop_screen()
            return

        if event.button.id == "btn-import":
            selected: dict[str, Path] = {}
            for key, path in self._files.items():
                chk = self.query_one(f"#chk-{key}", Checkbox)
                if chk.value:
                    selected[key] = path

            log = self.query_one("#migration-log", Log)

            if not selected:
                self.notify("Nothing selected.", severity="warning")
                return

            from mtproxymaxpy.config.migration import run_migration
            try:
                result = run_migration(files=selected)
                if result.settings_imported:
                    log.write_line("✓ settings.conf imported")
                if result.secrets_count:
                    log.write_line(f"✓ {result.secrets_count} secret(s) imported")
                if result.upstreams_count:
                    log.write_line(f"✓ {result.upstreams_count} upstream(s) imported")
                if result.instances_count:
                    log.write_line(f"✓ {result.instances_count} instance(s) imported")
                for err in result.errors:
                    log.write_line(f"✗ {err}")

                self.notify("Migration complete!", severity="information")
            except Exception as exc:
                log.write_line(f"✗ Migration failed: {exc}")
                self.notify(str(exc), severity="error")
                return

            self.query_one("#btn-import", Button).disabled = True
            self.query_one("#btn-skip", Button).label = "Continue →"
            self.query_one("#btn-skip", Button).variant = "success"
