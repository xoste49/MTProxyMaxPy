"""Entry point: TUI when run without arguments, CLI otherwise."""

from __future__ import annotations

import sys


def main() -> None:
    # If any CLI arguments are passed (excluding the interpreter), hand off to Typer.
    if len(sys.argv) > 1:
        from mtproxymaxpy.cli import app

        app()
    else:
        from mtproxymaxpy.tui.app import run_tui

        run_tui()


if __name__ == "__main__":
    main()
