"""In-memory persistence backend for rotation state."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from ..types import ProxyConfig
from .base import CooldownStore, PersistenceAdapter, ProxyStickyStore, StickyStore


@dataclass
class _StickyEntry:
    value: object
    expires_at: float


class MemoryStickyStore(StickyStore):
    def __init__(self) -> None:
        self._store: Dict[str, _StickyEntry] = {}

    def get(self, token: str):
        entry = self._store.get(token)
        if not entry:
            return None
        if entry.expires_at < time.monotonic():
            self._store.pop(token, None)
            return None
        return entry.value

    def set(self, token: str, value, ttl_seconds: int) -> None:
        self._store[token] = _StickyEntry(value=value, expires_at=time.monotonic() + ttl_seconds)

    def delete(self, token: str) -> None:
        self._store.pop(token, None)

    def prune(self) -> None:
        now = time.monotonic()
        expired = [token for token, entry in self._store.items() if entry.expires_at <= now]
        for token in expired:
            self._store.pop(token, None)


class MemoryProxyStickyStore(ProxyStickyStore, MemoryStickyStore):
    def __init__(self) -> None:
        MemoryStickyStore.__init__(self)

    def get(self, token: str) -> Optional[ProxyConfig]:  # type: ignore[override]
        value = MemoryStickyStore.get(self, token)
        if isinstance(value, ProxyConfig):
            return value
        if isinstance(value, dict):
            return ProxyConfig.model_validate(value)
        return None

    def set(self, token: str, proxy: ProxyConfig, ttl_seconds: int) -> None:  # type: ignore[override]
        MemoryStickyStore.set(self, token, proxy, ttl_seconds)


class MemoryCooldownStore(CooldownStore):
    def __init__(self) -> None:
        self._store: Dict[str, float] = {}

    def set(self, profile_id: str, expires_at: float) -> None:
        self._store[profile_id] = expires_at

    def get(self, profile_id: str) -> Optional[float]:
        expires = self._store.get(profile_id)
        if expires is None:
            return None
        if expires <= time.monotonic():
            self._store.pop(profile_id, None)
            return None
        return expires

    def remove(self, profile_id: str) -> None:
        self._store.pop(profile_id, None)

    def prune(self, now: float) -> Iterable[str]:
        expired = [profile_id for profile_id, expiry in self._store.items() if expiry <= now]
        for profile_id in expired:
            self._store.pop(profile_id, None)
        return expired


class MemoryPersistenceAdapter(PersistenceAdapter):
    def __init__(self) -> None:
        self._session_store = MemoryStickyStore()
        self._proxy_store = MemoryProxyStickyStore()
        self._cooldowns = MemoryCooldownStore()

    def sticky_sessions(self) -> StickyStore:
        return self._session_store

    def sticky_proxies(self) -> ProxyStickyStore:
        return self._proxy_store

    def cooldowns(self) -> CooldownStore:
        return self._cooldowns


__all__ = [
    "MemoryPersistenceAdapter",
    "MemoryStickyStore",
    "MemoryProxyStickyStore",
    "MemoryCooldownStore",
]
