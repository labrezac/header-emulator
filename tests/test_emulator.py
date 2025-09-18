import httpx
import pytest

from header_emulator import profile_loader as loader_module
from header_emulator.emulator import HeaderEmulator
from header_emulator.config import HeaderEmulatorConfig, ProxyPoolConfig
from header_emulator.providers.user_agents import UserAgentProvider, UserAgentRecord
from header_emulator.providers.locales import LocaleProvider
from header_emulator.providers.proxies import ProxyProvider
from header_emulator.types import LocaleProfile, ProxyConfig, ProxyScheme


def _providers():
    record = UserAgentRecord(
        id="alpha",
        family="Chrome",
        version="120.0",
        device="desktop",
        os="Windows 11",
        mobile=False,
        touch=False,
        original="Mozilla/5.0 test",
        weight=1.0,
        accept_header="text/html",
        accept_language_hint="en-US,en;q=0.9",
    )
    ua_provider = UserAgentProvider([record])
    locale_provider = LocaleProvider([LocaleProfile(language="en-US,en;q=0.9", country="US")])
    return ua_provider, locale_provider


def _emulator() -> HeaderEmulator:
    ua_provider, locale_provider = _providers()
    return HeaderEmulator(user_agents=ua_provider, locales=locale_provider)


def test_emulator_session_request():
    emulator = _emulator()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["User-Agent"].startswith("Mozilla/5.0 test")
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)

    with emulator.session(client_options={"transport": transport}) as session:
        response = session.request("GET", "https://example.com")
        assert response.json()["ok"] is True


def test_emulator_request_helper():
    emulator = _emulator()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    transport = httpx.MockTransport(handler)

    response = emulator.request(
        "GET",
        "https://example.com",
        session_kwargs={"client_options": {"transport": transport}},
    )
    assert response.text == "ok"


def test_emulator_next_headers_with_proxy():
    proxy = ProxyConfig(scheme=ProxyScheme.HTTP, host="127.0.0.1", port=8080)
    proxy_provider = ProxyProvider([proxy])
    config = HeaderEmulatorConfig(
        proxies=ProxyPoolConfig(preload=False, enabled=True, healthcheck_url=None),
    )
    ua_provider, locale_provider = _providers()
    emulator = HeaderEmulator(
        config=config,
        user_agents=ua_provider,
        locales=locale_provider,
        proxies=proxy_provider,
    )

    headers, chosen_proxy = emulator.next_headers(with_proxy=True)

    assert "User-Agent" in headers
    assert chosen_proxy is not None
    assert chosen_proxy.netloc == "127.0.0.1:8080"


@pytest.mark.anyio
async def test_emulator_async_session():
    emulator = _emulator()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"hello": "world"})

    transport = httpx.MockTransport(handler)

    async with emulator.async_session(client_options={"transport": transport}) as session:
        response = await session.request("GET", "https://example.com")
        assert response.json()["hello"] == "world"


def test_emulator_from_profile_file():
    payload = {
        "user_agents": [
            {
                "id": "alpha",
                "family": "Chrome",
                "version": "120.0",
                "device": "desktop",
                "os": "Windows",
                "mobile": False,
                "touch": False,
                "original": "Mozilla/5.0 test",
                "weight": 1.0,
                "accept_header": "text/html",
                "accept_language_hint": "en-US,en;q=0.9",
            }
        ],
        "locales": [
            {
                "language": "en-US,en;q=0.9",
                "country": "US",
            }
        ],
    }

    original_read = loader_module._read_file
    loader_module._read_file = lambda path: payload
    try:
        emulator = HeaderEmulator.from_profile_file("dummy.json")
    finally:
        loader_module._read_file = original_read

    headers, proxy = emulator.next_headers()
    assert "User-Agent" in headers
    assert proxy is None
