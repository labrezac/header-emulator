"""Helper functions for working with proxy providers."""

from __future__ import annotations

import time
import random
from typing import Iterable, List, Optional, Sequence

from .config import ProxyPoolConfig
from .providers import ProxyProvider, parse_proxy_url
from .proxy_manager import ProxyManager
from .types import ProxyConfig


def healthcheck_proxies(
    provider: ProxyProvider,
    *,
    config: Optional[ProxyPoolConfig] = None,
    client_factory=None,
) -> List[tuple[ProxyConfig, bool]]:
    """Return a list of `(proxy, ok)` tuples after running health checks."""

    pool_config = config or ProxyPoolConfig()
    manager = ProxyManager(
        provider,
        pool_config,
        client_factory=client_factory,
        time_fn=time.monotonic,
    )
    results: List[tuple[ProxyConfig, bool]] = []
    for proxy in provider.all():
        ok = manager.healthcheck(proxy)
        results.append((proxy, ok))
    return results


def load_proxies_from_lines(lines: Iterable[str]) -> ProxyProvider:
    """Create a provider from newline-delimited proxy URLs."""

    entries: list[ProxyConfig] = []
    for line in lines:
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        try:
            entries.append(parse_proxy_url(candidate))
        except ValueError:
            continue
    return ProxyProvider(entries)


def deduplicate_proxies(proxies: Iterable[ProxyConfig]) -> list[ProxyConfig]:
    """Remove duplicate proxies based on scheme/host/port."""

    seen: set[tuple[str, str, int]] = set()
    unique: list[ProxyConfig] = []
    for proxy in proxies:
        key = (proxy.scheme.value, proxy.host, proxy.port)
        if key in seen:
            continue
        seen.add(key)
        unique.append(proxy)
    return unique


def shuffled_proxies(proxies: Sequence[ProxyConfig], *, random_fn=None) -> list[ProxyConfig]:
    """Return a shuffled list of proxies."""

    random_fn = random_fn or random.shuffle
    shuffled = list(proxies)
    random_fn(shuffled)
    return shuffled


__all__ = ["healthcheck_proxies", "load_proxies_from_lines", "deduplicate_proxies", "shuffled_proxies"]
