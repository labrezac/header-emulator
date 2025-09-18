from header_emulator.builder import FETCH_INTENT_API, FETCH_INTENT_DOCUMENT, HeaderBuilder
from header_emulator.constants import DESKTOP_ACCEPT_HEADER
from header_emulator.providers.locales import LocaleProvider
from header_emulator.providers.proxies import ProxyProvider
from header_emulator.providers.user_agents import UserAgentProvider, UserAgentRecord
from header_emulator.types import LocaleProfile, ProxyConfig, ProxyScheme


def _single_record(record_id: str, mobile: bool = False) -> UserAgentRecord:
    return UserAgentRecord(
        id=record_id,
        family="Chrome",
        version="120.0",
        device="mobile" if mobile else "desktop",
        os="Android 14" if mobile else "Windows 11",
        mobile=mobile,
        touch=mobile,
        original="Mozilla/5.0 test",
        weight=1.0,
        accept_header=DESKTOP_ACCEPT_HEADER,
        accept_language_hint="en-US,en;q=0.9",
    )


def test_builder_creates_document_profile_with_referer():
    builder = HeaderBuilder(
        user_agents=UserAgentProvider([_single_record("desktop")]),
        locales=LocaleProvider([LocaleProfile(language="en-US,en;q=0.9", country="US")]),
        referers=["https://example.com/"],
    )

    profile = builder.create_profile(intent=FETCH_INTENT_DOCUMENT)

    assert profile.accept == DESKTOP_ACCEPT_HEADER
    assert profile.referer == "https://example.com/"
    assert profile.sec_fetch_mode == "navigate"
    assert profile.sec_fetch_site == "none"


def test_builder_applies_api_intent_headers():
    builder = HeaderBuilder(
        user_agents=UserAgentProvider([_single_record("desktop")]),
        locales=LocaleProvider([LocaleProfile(language="en-US,en;q=0.9", country="US")]),
        referers=[],
    )

    profile = builder.create_profile(intent=FETCH_INTENT_API)

    assert profile.accept != DESKTOP_ACCEPT_HEADER
    assert profile.upgrade_insecure_requests is None
    assert profile.sec_fetch_mode == "cors"
    assert profile.sec_fetch_site == "same-origin"


def test_builder_composes_emulated_request_with_proxy_and_overrides():
    proxy_provider = ProxyProvider(
        [
            ProxyConfig(scheme=ProxyScheme.HTTP, host="127.0.0.1", port=8080),
        ]
    )
    builder = HeaderBuilder(
        user_agents=UserAgentProvider([_single_record("desktop")]),
        locales=LocaleProvider([LocaleProfile(language="en-US,en;q=0.9", country="US")]),
        proxies=proxy_provider,
        referers=[],
    )

    request = builder.build_request(
        intent=FETCH_INTENT_DOCUMENT,
        headers_override={"X-Test": "1"},
        cookies={"session": "abc"},
        with_proxy=True,
    )

    assert request.headers["X-Test"] == "1"
    assert request.cookies == {"session": "abc"}
    assert request.proxy is not None
    assert request.proxy.netloc == "127.0.0.1:8080"
