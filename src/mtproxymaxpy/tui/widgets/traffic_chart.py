"""TrafficChart widget — sparkline from relay_stats files."""

from __future__ import annotations

from pathlib import Path
from textual.app import ComposeResult
from textual.widgets import Sparkline, Label
from textual.containers import Vertical

from mtproxymaxpy.constants import STATS_DIR


def _read_stats() -> list[float]:
    """Return a list of recent byte totals, one per stats file."""
    values: list[float] = []
    if not STATS_DIR.exists():
        return values
    for f in sorted(STATS_DIR.iterdir()):
        try:
            values.append(float(f.read_text().strip()))
        except Exception:
            values.append(0.0)
    return values or [0.0]


class TrafficChart(Vertical):
    """Shows a sparkline of per-user traffic bytes from relay_stats/."""

    DEFAULT_CSS = """
    TrafficChart {
        height: auto;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("[bold]Traffic (bytes per user)[/bold]")
        yield Sparkline(data=_read_stats(), id="traffic-sparkline")

    def refresh_data(self) -> None:
        sparkline = self.query_one("#traffic-sparkline", Sparkline)
        sparkline.data = _read_stats()
