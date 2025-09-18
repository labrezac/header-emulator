"""Integrations with third-party datasets for proxies and user agents.

These helpers rely on optional dependencies (`requests`, `proxyscrape`) or
public HTTP endpoints. They raise informative errors if the dependencies are
missing so the caller can decide whether to install them or fall back to local
files.
"""

from __future__ import annotations

import random
from typing import Iterable, Optional, Sequence, Tuple

from .providers.proxies import ProxyProvider, parse_proxy_url
from .providers.user_agents import UserAgentProvider, UserAgentRecord
from .types import LocaleProfile, ProxyConfig

_DEFAULT_PROXY_API = (
    "https://api.proxyscrape.com/v3/free-proxy-list/get"
    "?request=displayproxies&proxy_format=protocolipport&format=text"
)
_DEFAULT_INTOLI_URL = (
    "https://raw.githubusercontent.com/intoli/user-agents/master/dist/user-agents.json"
)


def proxies_from_proxyscrape(
    *,
    request_url: str = _DEFAULT_PROXY_API,
    session=None,
) -> ProxyProvider:
    """Fetch a proxy list using the proxyscrape API and return a provider.

    This function requires the `requests` library. It fetches text data where
    each line is a proxy URL (e.g. `http://host:port`).
    """

    response = _http_get(request_url, session=session)
    response.raise_for_status()
    lines = response.text.splitlines()
    proxies = [parse_proxy_url(line) for line in lines if line.strip()]
    return ProxyProvider(proxies)


def user_agents_from_intoli(
    *,
    request_url: str = _DEFAULT_INTOLI_URL,
    limit: Optional[int] = 100,
    include_mobile: bool = True,
    include_desktop: bool = True,
    session=None,
) -> Tuple[UserAgentProvider, LocaleProfile]:
    """Fetch user-agent data from the Intoli dataset.

    Returns a tuple of `(UserAgentProvider, default_locale_profile)`. The
    locale profile can be replaced with a more specific one by the caller.
    """

    if not include_mobile and not include_desktop:
        raise ValueError("At least one of include_mobile/include_desktop must be True")

    payload = _http_get(request_url, session=session).json()
    records = payload.get("user_agents", payload)

    ua_records: list[UserAgentRecord] = []
    for item in records:
        device_category = (item.get("deviceCategory") or item.get("deviceType") or "desktop").lower()
        is_mobile = device_category in {"mobile", "tablet", "phone"}
        if is_mobile and not include_mobile:
            continue
        if not is_mobile and not include_desktop:
            continue

        ua = item.get("userAgent") or item.get("user_agent")
        if not ua:
            continue

        family = item.get("browserName") or item.get("appName") or "Unknown"
        version = item.get("browserVersion") or item.get("appVersion")
        os_name = item.get("platform") or item.get("os") or "Unknown"

        record = UserAgentRecord(
            id=item.get("folder", "ua-") + str(len(ua_records)),
            family=family,
            version=version,
            device=device_category,
            os=os_name,
            mobile=is_mobile,
            touch=is_mobile,
            original=ua,
            weight=float(item.get("probability", 1.0)),
            accept_header=_accept_header_for_device(is_mobile),
            accept_language_hint=item.get("preferredLanguages", "en-US,en;q=0.9"),
        )
        ua_records.append(record)
        if limit is not None and len(ua_records) >= limit:
            break

    if not ua_records:
        raise RuntimeError("Intoli dataset did not yield any usable user agents")

    locale = LocaleProfile(language="en-US,en;q=0.9", country="US")
    return UserAgentProvider(ua_records), locale


def _accept_header_for_device(is_mobile: bool) -> str:
    if is_mobile:
        return (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        )
    return (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    )


def _http_get(url: str, *, session=None):
    requests = _import_requests()
    if session is None:
        return requests.get(url, timeout=10)
    return session.get(url, timeout=10)


def _import_requests():
    try:
        import requests
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("The 'requests' library is required for this function") from exc
    return requests


__all__ = ["proxies_from_proxyscrape", "user_agents_from_intoli"]
