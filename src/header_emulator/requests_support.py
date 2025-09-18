"""Integration helpers for using the emulator with the `requests` library."""

from __future__ import annotations

from typing import Optional

import requests

from .emulator import HeaderEmulator
from .types import ProxyConfig


def requests_request(
    emulator: HeaderEmulator,
    method: str,
    url: str,
    *,
    session: Optional[requests.Session] = None,
    with_proxy: bool = False,
    **kwargs,
):
    """Send a request using the emulator to supply headers (and optionally proxies).

    Parameters mirror ``requests.request`` with the addition of the emulator instance
    and a ``with_proxy`` flag to pull a proxy from the emulator's pool.
    """

    close_session = False
    if session is None:
        session = requests.Session()
        close_session = True

    try:
        emulated_request = emulator.next_request(with_proxy=with_proxy)

        # Merge headers/cookies
        headers = dict(emulated_request.headers)
        headers.update(kwargs.pop("headers", {}) or {})

        cookies = dict(emulated_request.cookies)
        cookies.update(kwargs.pop("cookies", {}) or {})

        proxies = kwargs.pop("proxies", None)
        if with_proxy and emulated_request.proxy is not None and proxies is None:
            proxies = _proxy_dict(emulated_request.proxy)

        response = session.request(
            method,
            url,
            headers=headers,
            cookies=cookies or None,
            proxies=proxies,
            **kwargs,
        )
        return response
    finally:
        if close_session:
            session.close()


def _proxy_dict(proxy: ProxyConfig) -> dict[str, str]:
    proxy_url = proxy.url
    return {"http": proxy_url, "https": proxy_url}


__all__ = ["requests_request"]
