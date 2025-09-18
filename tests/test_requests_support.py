import requests

from header_emulator.config import HeaderEmulatorConfig, ProxyPoolConfig
from header_emulator.emulator import HeaderEmulator
from header_emulator.requests_support import requests_request
from header_emulator.providers.user_agents import UserAgentProvider, UserAgentRecord
from header_emulator.providers.locales import LocaleProvider
from header_emulator.providers.proxies import ProxyProvider
from header_emulator.types import LocaleProfile, ProxyConfig, ProxyScheme


def _emulator(with_proxy: bool = False) -> HeaderEmulator:
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
    proxies = None
    config = HeaderEmulatorConfig()
    if with_proxy:
        proxies = ProxyProvider([ProxyConfig(scheme=ProxyScheme.HTTP, host="127.0.0.1", port=8888)])
        config = HeaderEmulatorConfig(
            proxies=ProxyPoolConfig(preload=False, enabled=True, healthcheck_url=None)
        )
    return HeaderEmulator(
        config=config,
        user_agents=ua_provider,
        locales=locale_provider,
        proxies=proxies,
    )


class DummySession(requests.Session):
    def __init__(self) -> None:
        super().__init__()
        self.captured = {}

    def request(self, method, url, **kwargs):  # pylint: disable=signature-differs
        self.captured = {
            "method": method,
            "url": url,
            **kwargs,
        }
        return "response"


def test_requests_request_merges_headers_and_cookies():
    emulator = _emulator()
    session = DummySession()

    response = requests_request(
        emulator,
        "GET",
        "https://example.com",
        session=session,
        headers={"X-Test": "1"},
        cookies={"session": "abc"},
    )

    assert response == "response"
    captured = session.captured
    assert captured["method"] == "GET"
    assert captured["headers"]["X-Test"] == "1"
    assert captured["cookies"]["session"] == "abc"
    assert "User-Agent" in captured["headers"]


def test_requests_request_applies_proxy_when_requested():
    emulator = _emulator(with_proxy=True)
    session = DummySession()

    requests_request(
        emulator,
        "GET",
        "https://example.com",
        session=session,
        with_proxy=True,
    )

    proxies = session.captured["proxies"]
    assert proxies["http"].startswith("http://")
    assert proxies["https"].startswith("http://")


def test_requests_request_respects_existing_session(monkeypatch):
    emulator = _emulator()
    session = DummySession()

    class DummyResponse:
        def __init__(self):
            self.text = "ok"

    monkeypatch.setattr(session, "request", lambda *args, **kwargs: DummyResponse())

    response = requests_request(
        emulator,
        "GET",
        "https://example.com",
        session=session,
        headers={"X-Test": "1"},
    )

    assert isinstance(response, DummyResponse)
