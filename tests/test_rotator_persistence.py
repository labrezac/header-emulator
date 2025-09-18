import pytest

from header_emulator.builder import HeaderBuilder
from header_emulator.config import CooldownConfig, HeaderEmulatorConfig
from header_emulator.persistence.memory import MemoryPersistenceAdapter
from header_emulator.providers.locales import LocaleProvider
from header_emulator.providers.user_agents import UserAgentProvider, UserAgentRecord
from header_emulator.rotator import HeaderRotator
from header_emulator.types import LocaleProfile, RotationStrategy


def _locale_provider():
    return LocaleProvider([LocaleProfile(language="en-US,en;q=0.9", country="US")])


def _builder(records):
    return HeaderBuilder(
        user_agents=UserAgentProvider(records),
        locales=_locale_provider(),
        referers=["https://example.com/"],
    )


def _record(identifier: str, weight: float = 1.0) -> UserAgentRecord:
    return UserAgentRecord(
        id=identifier,
        family="Chrome",
        version="120.0",
        device="desktop",
        os="Windows 11",
        mobile=False,
        touch=False,
        original=f"UA-{identifier}",
        weight=weight,
        accept_header="text/html",
        accept_language_hint="en-US,en;q=0.9",
    )


@pytest.mark.parametrize("adapter_factory", [MemoryPersistenceAdapter])
def test_sticky_profile_persists(adapter_factory):
    adapter = adapter_factory()
    builder = _builder([_record("alpha")])
    config = HeaderEmulatorConfig(rotation_strategy=RotationStrategy.STICKY)

    rotator_one = HeaderRotator(builder=builder, config=config, persistence=adapter)
    first = rotator_one.next_request(sticky_key="client-1")

    # Rebuild with the same adapter to simulate process restart
    rotator_two = HeaderRotator(builder=builder, config=config, persistence=adapter)
    second = rotator_two.next_request(sticky_key="client-1")

    assert first.profile_id == second.profile_id


@pytest.mark.parametrize("adapter_factory", [MemoryPersistenceAdapter])
def test_cooldown_persists(adapter_factory):
    adapter = adapter_factory()
    builder = _builder([_record("alpha", weight=0.5), _record("beta", weight=0.5)])
    config = HeaderEmulatorConfig(
        rotation_strategy=RotationStrategy.ROUND_ROBIN,
        cooldown=CooldownConfig(policy="cooldown", cooldown_seconds=60, failure_threshold=1),
    )

    rotator_one = HeaderRotator(builder=builder, config=config, persistence=adapter)
    first_profile = rotator_one.next_request().profile_id
    rotator_one.record_failure(first_profile)

    rotator_two = HeaderRotator(builder=builder, config=config, persistence=adapter)
    blocked_profile = rotator_two.next_request().profile_id

    assert blocked_profile != first_profile
