"""Proxy link building utilities.

FakeTLS secret format: ee + {key_hex} + {domain_ascii_as_hex}
  key    = "0123456789abcdef0123456789abcdef"  (32 hex chars = 16 bytes)
  domain = "cloudflare.com"
  hex    = "636c6f7564666c6172652e636f6d"
  result = "ee0123456789abcdef0123456789abcdef636c6f7564666c6172652e636f6d"
"""

from __future__ import annotations

import io
import urllib.parse


def build_faketls_secret(key: str, domain: str) -> str:
    """Return the full FakeTLS proxy secret string."""
    domain_hex = domain.encode("ascii").hex()
    return f"ee{key}{domain_hex}"


def build_proxy_links(
    key: str,
    domain: str,
    server: str,
    port: int,
) -> tuple[str, str]:
    """Return (tg:// link, https://t.me/ link) for a secret."""
    secret = build_faketls_secret(key, domain)
    params = f"server={server}&port={port}&secret={secret}"
    tg_link = f"tg://proxy?{params}"
    web_link = f"https://t.me/proxy?{params}"
    return tg_link, web_link


def qr_api_url(link: str) -> str:
    """Return an api.qrserver.com URL that generates a QR code image for *link*."""
    encoded = urllib.parse.quote(link, safe="")
    return f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={encoded}"


def render_qr_terminal(text: str) -> str | None:
    """Generate an ASCII QR code string using the qrcode library (if installed).

    Returns None if qrcode is not available.
    """
    try:
        import qrcode  # type: ignore[import]

        qr = qrcode.QRCode(border=1)
        qr.add_data(text)
        qr.make(fit=True)
        out = io.StringIO()
        qr.print_ascii(out=out)
        return out.getvalue()
    except ImportError:
        return None
