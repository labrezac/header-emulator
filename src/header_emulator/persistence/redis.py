"""Redis-backed persistence adapter."""

from __future__ import annotations

import json
import time
from typing import Iterable, Optional

try:
    import redis
except ImportError:  # pragma: no cover - optional dependency
    redis = None

from .base import CooldownStore, PersistenceAdapter, ProxyStickyStore, StickyStore
from ..types import ProxyConfig


class RedisPersistenceAdapter(PersistenceAdapter):
    """Persistence adapter backed by Redis."""

    def __init__(self, dsn: str = "redis://localhost:6379/0", *, namespace: str = "header_emulator") -> None:
        if redis is None:
            raise RuntimeError("redis-py is required for RedisPersistenceAdapter")
        self._redis = redis.Redis.from_url(dsn)
        self._ns = namespace
        self._sticky_sessions = RedisStickyStore(self._redis, namespace)
        self._sticky_proxies = RedisProxyStickyStore(self._redis, namespace)
        self._cooldowns = RedisCooldownStore(self._redis, namespace)

    def sticky_sessions(self) -> StickyStore:
        return self._sticky_sessions

    def sticky_proxies(self) -> ProxyStickyStore:
        return self._sticky_proxies

    def cooldowns(self) -> CooldownStore:
        return self._cooldowns


class RedisStickyStore(StickyStore):
    def __init__(self, client: "redis.Redis", namespace: str) -> None:
        self._client = client
        self._key = f"{namespace}:sticky_sessions"

    def get(self, token: str) -> Optional[str]:
        value = self._client.hget(self._key, token)
        return value.decode("utf-8") if value else None

    def set(self, token: str, profile_id: str, ttl_seconds: int) -> None:
        pipe = self._client.pipeline()
        pipe.hset(self._key, token, profile_id)
        pipe.expire(self._key, ttl_seconds)
        pipe.execute()

    def delete(self, token: str) -> None:
        self._client.hdel(self._key, token)

    def prune(self) -> None:
        pass  # Redis handles TTL on the hash key


class RedisProxyStickyStore(ProxyStickyStore):
    def __init__(self, client: "redis.Redis", namespace: str) -> None:
        self._client = client
        self._key = f"{namespace}:sticky_proxies"

    def get(self, token: str) -> Optional[ProxyConfig]:
        value = self._client.hget(self._key, token)
        if not value:
            return None
        payload = json.loads(value)
        return ProxyConfig.model_validate(payload)

    def set(self, token: str, proxy: ProxyConfig, ttl_seconds: int) -> None:
        pipe = self._client.pipeline()
        pipe.hset(self._key, token, proxy.model_dump_json())
        pipe.expire(self._key, ttl_seconds)
        pipe.execute()

    def delete(self, token: str) -> None:
        self._client.hdel(self._key, token)

    def prune(self) -> None:
        pass


class RedisCooldownStore(CooldownStore):
    def __init__(self, client: "redis.Redis", namespace: str) -> None:
        self._client = client
        self._key = f"{namespace}:cooldowns"

    def set(self, profile_id: str, expires_at: float) -> None:
        self._client.zadd(self._key, {profile_id: expires_at})

    def get(self, profile_id: str) -> Optional[float]:
        score = self._client.zscore(self._key, profile_id)
        if score is None:
            return None
        if score <= time.time():
            self.remove(profile_id)
            return None
        return float(score)

    def remove(self, profile_id: str) -> None:
        self._client.zrem(self._key, profile_id)

    def prune(self, now: float) -> Iterable[str]:
        expired = self._client.zrangebyscore(self._key, "-inf", now)
        if expired:
            self._client.zremrangebyscore(self._key, "-inf", now)
        return [entry.decode("utf-8") for entry in expired]


__all__ = ["RedisPersistenceAdapter"]
