"""StatusBox widget — coloured proxy status block."""

from textual.app import ComposeResult
from textual.widgets import Static
from textual.reactive import reactive


class StatusBox(Static):
    """Displays a labelled status indicator that updates reactively."""

    running: reactive[bool] = reactive(False)

    def __init__(self, label: str = "mtproxymaxpy", **kwargs) -> None:
        super().__init__(**kwargs)
        self._label = label

    def render(self) -> str:
        icon = "●" if self.running else "○"
        color = "green" if self.running else "red"
        state = "RUNNING" if self.running else "STOPPED"
        return f"[bold {color}]{icon} {self._label}  —  {state}[/bold {color}]"

    def refresh_status(self) -> None:
        from mtproxymaxpy import process_manager

        self.running = process_manager.is_running()
