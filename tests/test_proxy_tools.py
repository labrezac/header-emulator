import httpx

from header_emulator.config import ProxyPoolConfig
from header_emulator.providers.proxies import ProxyProvider
from header_emulator.types import ProxyConfig, ProxyScheme
from header_emulator.proxy_tools import (
    deduplicate_proxies,
    healthcheck_proxies,
    load_proxies_from_lines,
    shuffled_proxies,
)
from header_emulator.utils import weighted_choice


class DummyClient(httpx.Client):
    def __init__(self, ok: bool) -> None:
        super().__init__()
        self._ok = ok

    def get(self, *args, **kwargs):  # pylint: disable=signature-differs
        return httpx.Response(200 if self._ok else 500)

    def close(self) -> None:
        super().close()


def _provider() -> ProxyProvider:
    proxies = [
        ProxyConfig(scheme=ProxyScheme.HTTP, host="127.0.0.1", port=8000),
        ProxyConfig(scheme=ProxyScheme.HTTP, host="127.0.0.2", port=8001),
    ]
    return ProxyProvider(proxies)


def test_healthcheck_proxies_uses_client_factory():
    provider = _provider()

    def factory(proxy: ProxyConfig) -> httpx.Client:
        ok = proxy.host.endswith(".1")
        return DummyClient(ok)

    results = healthcheck_proxies(
        provider,
        config=ProxyPoolConfig(preload=False),
        client_factory=factory,
    )

    assert len(results) == 2
    first_proxy, first_ok = results[0]
    second_proxy, second_ok = results[1]
    assert first_proxy.host.endswith(".1")
    assert first_ok is True
    assert second_proxy.host.endswith(".2")
    assert second_ok is False


def test_healthcheck_proxies_defaults_to_config_url():
    provider = _provider()

    def factory(_: ProxyConfig) -> httpx.Client:
        return DummyClient(True)

    results = healthcheck_proxies(
        provider,
        config=ProxyPoolConfig(healthcheck_url="https://example.com/status", preload=False),
        client_factory=factory,
    )

    assert all(ok for _, ok in results)


def test_load_proxies_from_lines_parses_entries():
    lines = ["http://user:pass@127.0.0.1:8000", "# comment", "  ", "http://127.0.0.2:8001"]
    provider = load_proxies_from_lines(lines)
    proxies = provider.all()
    assert len(proxies) == 2
    assert proxies[0].netloc == "127.0.0.1:8000"
    assert proxies[1].netloc == "127.0.0.2:8001"


def test_deduplicate_proxies_removes_duplicates():
    proxies = [
        ProxyConfig(scheme=ProxyScheme.HTTP, host="127.0.0.1", port=8000),
        ProxyConfig(scheme=ProxyScheme.HTTP, host="127.0.0.1", port=8000),
        ProxyConfig(scheme=ProxyScheme.HTTP, host="127.0.0.2", port=8000),
    ]
    unique = deduplicate_proxies(proxies)
    assert len(unique) == 2


def test_shuffled_proxies_uses_random_function():
    proxies = [
        ProxyConfig(scheme=ProxyScheme.HTTP, host="127.0.0.1", port=8000),
        ProxyConfig(scheme=ProxyScheme.HTTP, host="127.0.0.2", port=8001),
    ]

    def reverse(seq):
        seq.reverse()

    shuffled = shuffled_proxies(proxies, random_fn=reverse)
    assert shuffled[0].host == "127.0.0.2"


def test_weighted_choice_handles_zero_weights():
    proxies = [ProxyConfig(scheme=ProxyScheme.HTTP, host="a", port=1), ProxyConfig(scheme=ProxyScheme.HTTP, host="b", port=2)]
    chosen = weighted_choice(proxies, [0.0, 0.0], random_fn=lambda: 0.0)
    assert chosen.host in {"a", "b"}
