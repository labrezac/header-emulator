import pytest

from header_emulator.providers.proxies import ProxyProvider, parse_proxy_url
from header_emulator.types import ProxyScheme


def test_parse_proxy_url_with_auth_defaults():
    proxy = parse_proxy_url("http://user:pass@example.com")
    assert proxy.scheme is ProxyScheme.HTTP
    assert proxy.netloc == "example.com:80"
    assert proxy.auth.username == "user"
    assert proxy.auth.password == "pass"


def test_parse_proxy_url_invalid():
    with pytest.raises(ValueError):
        parse_proxy_url("not-a-valid-url")


def test_proxy_provider_from_env(monkeypatch):
    monkeypatch.setenv("PROXY_URLS", "http://127.0.0.1:8080, https://example.com:9000")
    provider = ProxyProvider.from_env()
    proxies = provider.all()
    assert proxies[0].netloc == "127.0.0.1:8080"
    assert proxies[1].scheme is ProxyScheme.HTTPS
