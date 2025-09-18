"""Proxy provider utilities following ZenRows rotation practices."""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import urlparse

from pydantic import ValidationError

from ..types import ProxyAuth, ProxyConfig, ProxyScheme


def parse_proxy_url(url: str, *, weight: float = 1.0) -> ProxyConfig:
    """Parse a proxy URL into a configuration object."""

    parsed = urlparse(url.strip())
    if not parsed.hostname:
        raise ValueError(f"Proxy URL missing hostname: {url}")
    scheme = ProxyScheme(parsed.scheme or "http")
    auth = None
    if parsed.username and parsed.password:
        auth = ProxyAuth(username=parsed.username, password=parsed.password)
    port = parsed.port
    if port is None:
        port = 443 if scheme in (ProxyScheme.HTTPS,) else 80
    return ProxyConfig(
        scheme=scheme,
        host=parsed.hostname,
        port=port,
        auth=auth,
        weight=weight,
    )


class ProxyProvider:
    """Loads proxy configurations from multiple sources."""

    def __init__(self, proxies: Sequence[ProxyConfig] | None = None) -> None:
        self._proxies: list[ProxyConfig] = list(proxies or [])

    def all(self) -> list[ProxyConfig]:
        return list(self._proxies)

    def extend(self, proxies: Iterable[ProxyConfig]) -> None:
        for proxy in proxies:
            self._proxies.append(proxy)

    @classmethod
    def from_env(cls, env_var: str = "PROXY_URLS") -> "ProxyProvider":
        raw = os.getenv(env_var)
        if not raw:
            return cls([])
        proxies = [parse_proxy_url(item) for item in raw.split(",") if item.strip()]
        return cls(proxies)

    @classmethod
    def from_file(cls, path: str | Path) -> "ProxyProvider":
        entries: list[ProxyConfig] = []
        with Path(path).open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                entries.append(parse_proxy_url(line))
        return cls(entries)

    @classmethod
    def from_csv(
        cls,
        path: str | Path,
        *,
        url_field: str = "proxy",
        weight_field: str | None = "weight",
    ) -> "ProxyProvider":
        entries: list[ProxyConfig] = []
        with Path(path).open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                url = row.get(url_field)
                if not url:
                    continue
                weight_value = 1.0
                if weight_field and row.get(weight_field):
                    try:
                        weight_value = float(row[weight_field])
                    except ValueError:
                        weight_value = 1.0
                try:
                    entries.append(parse_proxy_url(url, weight=weight_value))
                except (ValueError, ValidationError):
                    continue
        return cls(entries)


__all__ = ["ProxyProvider", "parse_proxy_url"]
