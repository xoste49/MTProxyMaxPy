"""ProxyLink widget — renders a clickable mtproto:// link and ASCII QR code."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static, Label
from textual.containers import Vertical


def _build_link(ip: str, port: int, secret: str, domain: str) -> str:
    return f"tg://proxy?server={ip}&port={port}&secret=ee{secret}&domain={domain}"


def _qr_text(data: str) -> str:
    try:
        import qrcode
        from io import StringIO
        qr = qrcode.QRCode(border=1)
        qr.add_data(data)
        qr.make(fit=True)
        sio = StringIO()
        qr.print_ascii(out=sio, invert=True)
        return sio.getvalue()
    except Exception:
        return "(qrcode package not available)"


class ProxyLink(Vertical):
    """Shows proxy URL and QR for a single secret."""

    DEFAULT_CSS = """
    ProxyLink {
        height: auto;
        padding: 1;
        border: round $accent;
    }
    """

    def __init__(self, ip: str, port: int, secret: str, domain: str, label: str = "", **kwargs):
        super().__init__(**kwargs)
        self._url = _build_link(ip, port, secret, domain)
        self._label = label

    def compose(self) -> ComposeResult:
        if self._label:
            yield Label(f"[bold]{self._label}[/bold]")
        yield Static(f"[link={self._url}]{self._url}[/link]", markup=True)
        yield Static(_qr_text(self._url))
