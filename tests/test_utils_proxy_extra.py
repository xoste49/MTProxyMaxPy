from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING

from mtproxymaxpy.utils import proxy_link, validation

if TYPE_CHECKING:
    import pytest


def test_proxy_link_builders_and_qr_url() -> None:
    secret = proxy_link.build_faketls_secret("a" * 32, "cloudflare.com")
    assert secret.startswith("ee" + "a" * 32)
    assert secret.endswith("cloudflare.com".encode("ascii").hex())

    tg, web = proxy_link.build_proxy_links("a" * 32, "cloudflare.com", "1.2.3.4", 443)
    assert tg.startswith("tg://proxy?")
    assert web.startswith("https://t.me/proxy?")
    assert "server=1.2.3.4" in tg

    qr = proxy_link.qr_api_url(tg)
    assert "api.qrserver.com" in qr
    assert "%3A%2F%2F" in qr


def test_render_qr_terminal_success_and_importerror(monkeypatch: pytest.MonkeyPatch) -> None:
    class _QR:
        def __init__(self, border=1):
            self.value = None

        def add_data(self, value):
            self.value = value

        def make(self, fit=True):
            return None

        def print_ascii(self, out=None):
            out.write("QR\n")

    monkeypatch.setitem(sys.modules, "qrcode", SimpleNamespace(QRCode=_QR))
    assert "QR" in (proxy_link.render_qr_terminal("hello") or "")

    monkeypatch.delitem(sys.modules, "qrcode", raising=False)

    class _Importer:
        def __call__(self, name, *args, **kwargs):
            if name == "qrcode":
                raise ImportError("no qrcode")
            return __import__(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _Importer())
    assert proxy_link.render_qr_terminal("hello") is None


def test_is_port_available_branches() -> None:
    assert validation.is_port_available(0) is True


def test_is_port_available_oserror_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Sock:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def setsockopt(self, *a, **k):
            return None

        def bind(self, *a, **k):
            raise OSError("in use")

    monkeypatch.setattr(validation.socket, "socket", lambda *a, **k: _Sock())
    assert validation.is_port_available(443, host="127.0.0.1") is False
