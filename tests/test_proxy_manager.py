import math

import httpx
import pytest

from header_emulator.config import ProxyPoolConfig
from header_emulator.providers.proxies import ProxyProvider
from header_emulator.proxy_manager import ProxyManager
from header_emulator.types import FailurePolicy, ProxyConfig, ProxyScheme, RotationStrategy


class TimeStub:
    def __init__(self) -> None:
        self.current = 0.0

    def advance(self, delta: float) -> None:
        self.current += delta

    def __call__(self) -> float:
        return self.current


class DummyClient(httpx.Client):
    def __init__(self, ok: bool) -> None:
        super().__init__()
        self._ok = ok

    def get(self, *args, **kwargs):
        return httpx.Response(200 if self._ok else 500)

    def close(self) -> None:  # pragma: no cover - no resources to free
        super().close()


def _provider(count: int = 2) -> ProxyProvider:
    proxies = [
        ProxyConfig(scheme=ProxyScheme.HTTP, host=f"127.0.0.{idx+1}", port=8000 + idx, weight=idx + 1)
        for idx in range(count)
    ]
    return ProxyProvider(proxies)


def test_proxy_selection_weighted():
    provider = _provider(3)
    config = ProxyPoolConfig(rotation_strategy=RotationStrategy.WEIGHTED, preload=False)
    manager = ProxyManager(provider, config)

    selections = {proxy.url: 0 for proxy in provider.all()}
    for _ in range(200):
        proxy = manager.select()
        selections[proxy.url] += 1

    # ensure each proxy was selected at least once
    assert all(count > 0 for count in selections.values())


def test_proxy_cooldown_on_failure():
    provider = _provider(2)
    time_stub = TimeStub()
    config = ProxyPoolConfig(
        rotation_strategy=RotationStrategy.ROUND_ROBIN,
        failure_policy=FailurePolicy.COOLDOWN,
        failure_threshold=1,
        cooldown_seconds=10,
        preload=False,
    )
    manager = ProxyManager(provider, config, time_fn=time_stub)

    first_proxy = manager.select()
    manager.mark_failure(first_proxy)
    next_proxy = manager.select()

    assert next_proxy.url != first_proxy.url

    time_stub.advance(10)
    replay_proxy = manager.select()
    assert replay_proxy.url == first_proxy.url


def test_proxy_preload_healthcheck_filters():
    provider = _provider(2)
    config = ProxyPoolConfig(preload=True)

    def client_factory(proxy: ProxyConfig) -> httpx.Client:
        ok = proxy.host.endswith(".1")
        return DummyClient(ok=ok)

    manager = ProxyManager(provider, config, client_factory=client_factory)

    proxy = manager.select()
    assert proxy.host.endswith(".1")


def test_proxy_manager_failure_threshold_triggers_cooldown():
    provider = ProxyProvider(
        [ProxyConfig(scheme=ProxyScheme.HTTP, host="10.0.0.1", port=8080, weight=1.0)]
    )
    config = ProxyPoolConfig(
        rotation_strategy=RotationStrategy.RANDOM,
        failure_policy=FailurePolicy.COOLDOWN,
        failure_threshold=2,
        cooldown_seconds=5,
        preload=False,
    )
    time_stub = TimeStub()
    manager = ProxyManager(provider, config, time_fn=time_stub)

    proxy = manager.select()
    manager.mark_failure(proxy)
    # First failure below threshold -> still selectable
    assert manager.select().url == proxy.url

    manager.mark_failure(proxy)
    with pytest.raises(RuntimeError):
        manager.select()
