"""Network utilities: public IP detection, port availability."""

import logging
import time

import httpx

from mtproxymaxpy.constants import PUBLIC_IP_CACHE_TTL, PUBLIC_IP_ENDPOINTS

_log = logging.getLogger(__name__)
_ip_cache: tuple[str, float] | None = None


def get_public_ip(timeout: float = 5.0) -> str | None:
    """Return the server's public IPv4 address.

    Results are cached for PUBLIC_IP_CACHE_TTL seconds.
    Returns None if all endpoints fail.
    """
    global _ip_cache
    now = time.monotonic()
    if _ip_cache is not None:
        ip, ts = _ip_cache
        if now - ts < PUBLIC_IP_CACHE_TTL:
            return ip

    for url in PUBLIC_IP_ENDPOINTS:
        try:
            resp = httpx.get(url, timeout=timeout, follow_redirects=True)
            resp.raise_for_status()
            text = resp.text.strip()
            # ipify returns JSON {"ip": "..."}
            if text.startswith("{"):
                import json

                text = json.loads(text).get("ip", "")
            if text:
                _ip_cache = (text, now)
                return text
        except Exception:
            _log.debug("IP lookup failed for endpoint", exc_info=True)
            continue
    return None
