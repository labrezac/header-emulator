import pytest

from header_emulator import profile_loader


def test_load_profiles_from_json(monkeypatch):
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

    monkeypatch.setattr(profile_loader, "_read_file", lambda path: payload)
    ua_provider, locale_provider = profile_loader.load_profiles("dummy.json")

    assert ua_provider.random().id == "alpha"
    assert locale_provider.random().country == "US"


def test_load_profiles_yaml_requires_pyyaml(monkeypatch):
    payload = {"user_agents": [], "locales": []}

    monkeypatch.setattr(profile_loader, "_read_file", lambda path: payload)

    pytest.importorskip("yaml")
    profile_loader.load_profiles("dummy.yaml")
