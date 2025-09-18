import types

import pytest

from header_emulator import external_sources


class DummyResponse:
    def __init__(self, text=None, json_data=None):
        self.text = text or ""
        self._json = json_data

    def raise_for_status(self):
        return None

    def json(self):
        return self._json


def test_proxies_from_proxyscrape(monkeypatch):
    proxy_text = "http://127.0.0.1:8080\nhttps://example.com:9000"
    monkeypatch.setattr(
        external_sources,
        "_http_get",
        lambda url, session=None: DummyResponse(text=proxy_text),
    )

    provider = external_sources.proxies_from_proxyscrape()
    proxies = provider.all()
    assert proxies[0].netloc == "127.0.0.1:8080"
    assert proxies[1].scheme.value == "https"


def test_user_agents_from_intoli(monkeypatch):
    payload = {
        "user_agents": [
            {
                "userAgent": "Mozilla/5.0 test",
                "browserName": "Chrome",
                "browserVersion": "120.0.0.0",
                "platform": "Windows 11",
                "deviceCategory": "desktop",
                "probability": 0.5,
                "preferredLanguages": "en-US,en;q=0.9",
            }
        ]
    }
    monkeypatch.setattr(
        external_sources,
        "_http_get",
        lambda url, session=None: DummyResponse(json_data=payload),
    )

    provider, locale = external_sources.user_agents_from_intoli(limit=1)
    record = provider.random()
    assert record.original == "Mozilla/5.0 test"
    assert record.family == "Chrome"
    assert locale.language == "en-US,en;q=0.9"
