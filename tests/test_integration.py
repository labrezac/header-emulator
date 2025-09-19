import httpx
import pytest

from header_emulator import (
    HeaderEmulator,
    requests_request,
)
from header_emulator.config import HeaderEmulatorConfig, ProxyPoolConfig
from header_emulator.providers.proxies import ProxyProvider
from header_emulator.types import ProxyConfig, ProxyScheme


PROFILE_PAYLOAD = {
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


@pytest.fixture
def emulator(monkeypatch):
    monkeypatch.setattr("header_emulator.profile_loader._read_file", lambda path: PROFILE_PAYLOAD)
    proxy_provider = ProxyProvider(
        [ProxyConfig(scheme=ProxyScheme.HTTP, host="127.0.0.1", port=8000)]
    )
    config = HeaderEmulatorConfig(
        proxies=ProxyPoolConfig(preload=False, enabled=True, healthcheck_url=None)
    )
    return HeaderEmulator.from_profile_file("ignored.json", config=config, proxies=proxy_provider)


def test_httpx_session_with_proxy(emulator):
    captured = {}

    def handler(request):
        captured["headers"] = request.headers
        return httpx.Response(200, text="ok")

    transport = httpx.MockTransport(handler)
    with emulator.session(client_options={"transport": transport}) as session:
        response = session.request("GET", "https://example.com")

    assert response.status_code == 200
    assert captured["headers"]["User-Agent"] == "Mozilla/5.0 test"


def test_requests_helper_with_proxy(emulator):
    captured = {}

    class DummySession:
        def request(self, method, url, **kwargs):
            captured.update({"method": method, "url": url, **kwargs})
            return type("Resp", (), {"text": "ok"})()

    session = DummySession()

    response = requests_request(
        emulator,
        "GET",
        "https://example.com",
        session=session,
        with_proxy=True,
    )

    assert response.text == "ok"
    assert captured["proxies"]["http"].startswith("http://")
