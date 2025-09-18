import os
import pytest

from header_emulator.persistence.redis import RedisPersistenceAdapter
from header_emulator.types import ProxyConfig, ProxyScheme

pytestmark = pytest.mark.skipif(
    os.getenv("REDIS_URL") is None,
    reason="Requires REDIS_URL environment variable",
)


@pytest.fixture()
def adapter():
    url = os.getenv("REDIS_URL")
    return RedisPersistenceAdapter(dsn=url, namespace="test_header_emulator")


def test_redis_sticky_round_trip(adapter):
    store = adapter.sticky_sessions()
    store.set("token", "profile", ttl_seconds=5)
    assert store.get("token") == "profile"
    store.delete("token")
    assert store.get("token") is None


def test_redis_proxy_round_trip(adapter):
    store = adapter.sticky_proxies()
    proxy = ProxyConfig(scheme=ProxyScheme.HTTP, host="localhost", port=8888)
    store.set("token", proxy, ttl_seconds=5)
    stored = store.get("token")
    assert stored is not None
    assert stored.netloc == "localhost:8888"


def test_redis_cooldown_prune(adapter):
    store = adapter.cooldowns()
    store.set("profile", 0)
    expired = list(store.prune(1))
    assert "profile" in expired

