import time

import pytest

from header_emulator.persistence.memory import MemoryPersistenceAdapter
from header_emulator.types import ProxyConfig, ProxyScheme


@pytest.mark.parametrize("adapter_factory", [MemoryPersistenceAdapter])
def test_sticky_store_round_trip(adapter_factory):
    adapter = adapter_factory()
    store = adapter.sticky_sessions()
    store.set("token", "profile", ttl_seconds=1)
    assert store.get("token") == "profile"
    store.delete("token")
    assert store.get("token") is None


@pytest.mark.parametrize("adapter_factory", [MemoryPersistenceAdapter])
def test_sticky_store_expiry(adapter_factory):
    adapter = adapter_factory()
    store = adapter.sticky_sessions()
    store.set("token", "profile", ttl_seconds=0)
    time.sleep(0.01)
    assert store.get("token") is None


@pytest.mark.parametrize("adapter_factory", [MemoryPersistenceAdapter])
def test_proxy_sticky_store(adapter_factory):
    adapter = adapter_factory()
    store = adapter.sticky_proxies()
    proxy = ProxyConfig(scheme=ProxyScheme.HTTP, host="localhost", port=8080)
    store.set("token", proxy, ttl_seconds=1)
    result = store.get("token")
    assert result is not None
    assert result.netloc == "localhost:8080"


@pytest.mark.parametrize("adapter_factory", [MemoryPersistenceAdapter])
def test_cooldown_store(adapter_factory):
    adapter = adapter_factory()
    store = adapter.cooldowns()
    now = time.time()
    store.set("profile", now + 0.1)
    assert store.get("profile") is not None
    expired = store.prune(now + 1)
    assert "profile" in list(expired)
    assert store.get("profile") is None
