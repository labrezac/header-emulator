import pytest

from header_emulator.builder import HeaderBuilder
from header_emulator.config import CooldownConfig, HeaderEmulatorConfig
from header_emulator.providers.locales import LocaleProvider
from header_emulator.providers.proxies import ProxyProvider
from header_emulator.providers.user_agents import UserAgentProvider, UserAgentRecord
from header_emulator.rotator import HeaderRotator
from header_emulator.types import LocaleProfile, ProxyConfig, ProxyScheme, RotationStrategy, StickySessionKey


def _record(record_id: str, weight: float) -> UserAgentRecord:
    return UserAgentRecord(
        id=record_id,
        family="Chrome",
        version="120.0",
        device="desktop",
        os="Windows 11",
        mobile=False,
        touch=False,
        original=f"UA-{record_id}",
        weight=weight,
        accept_header="text/html",
        accept_language_hint="en-US,en;q=0.9",
    )


def _builder(with_proxy: bool = False) -> HeaderBuilder:
    ua_provider = UserAgentProvider([_record("alpha", 0.7), _record("beta", 0.3)])
    locale_provider = LocaleProvider([LocaleProfile(language="en-US,en;q=0.9", country="US")])
    proxy_provider = None
    if with_proxy:
        proxy_provider = ProxyProvider(
            [ProxyConfig(scheme=ProxyScheme.HTTP, host="10.0.0.1", port=3128)]
        )
    return HeaderBuilder(
        user_agents=ua_provider,
        locales=locale_provider,
        proxies=proxy_provider,
        referers=["https://example.com/"],
    )


def test_round_robin_rotation_cycles_profiles():
    config = HeaderEmulatorConfig(rotation_strategy=RotationStrategy.ROUND_ROBIN)
    rotator = HeaderRotator(builder=_builder(), config=config)

    first = rotator.next_request().profile_id
    second = rotator.next_request().profile_id
    third = rotator.next_request().profile_id

    assert first == "alpha"
    assert second == "beta"
    assert third == "alpha"


def test_sticky_strategy_reuses_profile_and_proxy():
    config = HeaderEmulatorConfig(rotation_strategy=RotationStrategy.STICKY)
    rotator = HeaderRotator(builder=_builder(with_proxy=True), config=config)

    first = rotator.next_request(sticky_key="client-1", with_proxy=True)
    second = rotator.next_request(sticky_key="client-1", with_proxy=True)

    assert first.profile_id == second.profile_id
    assert first.proxy is not None
    assert second.proxy is not None
    assert first.proxy.url == second.proxy.url


def test_failure_triggers_cooldown():
    config = HeaderEmulatorConfig(
        rotation_strategy=RotationStrategy.ROUND_ROBIN,
        cooldown=CooldownConfig(policy="cooldown", cooldown_seconds=60, failure_threshold=1),
    )
    rotator = HeaderRotator(builder=_builder(), config=config)

    first = rotator.next_request().profile_id
    rotator.record_failure(first)
    second = rotator.next_request().profile_id

    assert second != first


def test_rotator_requires_profiles():
    class EmptyProvider(UserAgentProvider):
        def __init__(self):
            self._records = []
            self._index = {}

        def all(self):
            return []

    ua_provider = EmptyProvider()
    locale_provider = LocaleProvider([LocaleProfile(language="en-US,en;q=0.9", country="US")])
    builder = HeaderBuilder(user_agents=ua_provider, locales=locale_provider)
    config = HeaderEmulatorConfig()

    with pytest.raises(ValueError):
        HeaderRotator(builder=builder, config=config)
