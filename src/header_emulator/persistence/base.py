"""Persistence interfaces for storing rotation state."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Optional, Protocol

from ..types import ProxyConfig, StickySessionKey


class StickyStore(Protocol):
    """Protocol for storing sticky session mappings."""

    def get(self, token: str) -> Optional[str]:
        ...

    def set(self, token: str, profile_id: str, ttl_seconds: int) -> None:
        ...

    def delete(self, token: str) -> None:
        ...

    def prune(self) -> None:
        ...


class ProxyStickyStore(Protocol):
    def get(self, token: str) -> Optional[ProxyConfig]:
        ...

    def set(self, token: str, proxy: ProxyConfig, ttl_seconds: int) -> None:
        ...

    def delete(self, token: str) -> None:
        ...

    def prune(self) -> None:
        ...


class CooldownStore(Protocol):
    def set(self, profile_id: str, expires_at: float) -> None:
        ...

    def get(self, profile_id: str) -> Optional[float]:
        ...

    def remove(self, profile_id: str) -> None:
        ...

    def prune(self, now: float) -> Iterable[str]:
        ...


class PersistenceAdapter(ABC):
    """Base class that returns store implementations."""

    @abstractmethod
    def sticky_sessions(self) -> StickyStore:
        raise NotImplementedError

    @abstractmethod
    def sticky_proxies(self) -> ProxyStickyStore:
        raise NotImplementedError

    @abstractmethod
    def cooldowns(self) -> CooldownStore:
        raise NotImplementedError
