import anyio
import httpx

from header_emulator.builder import HeaderBuilder
from header_emulator.config import (
    CooldownConfig,
    HeaderEmulatorConfig,
    ProxyPoolConfig,
    RetryConfig,
    TelemetryConfig,
    ThrottleConfig,
)
from header_emulator.persistence.memory import MemoryPersistenceAdapter
from header_emulator.providers.locales import LocaleProvider
from header_emulator.providers.proxies import ProxyProvider
from header_emulator.providers.user_agents import UserAgentProvider, UserAgentRecord
from header_emulator.proxy_manager import ProxyManager
from header_emulator.rotator import HeaderRotator
from header_emulator.session import AsyncHeaderSession, HeaderSession
from header_emulator.telemetry import InMemoryTelemetrySink, TelemetryPublisher
from header_emulator.types import LocaleProfile, ProxyConfig, ProxyScheme, RotationStrategy


class Collector:
    def __init__(self) -> None:
        self.events = []

    def handle(self, event):
        self.events.append(event)


def _builder() -> HeaderBuilder:
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
    return HeaderBuilder(
        user_agents=UserAgentProvider([record]),
        locales=LocaleProvider([LocaleProfile(language="en-US,en;q=0.9", country="US")]),
        referers=["https://example.com/"],
    )


def test_sync_session_emits_success_event():
    collector = Collector()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    config = HeaderEmulatorConfig(
        retry=RetryConfig(max_attempts=1, backoff_factor=0.1, jitter_seconds=0.0),
        throttle=ThrottleConfig(enabled=False),
        telemetry=TelemetryConfig(enabled=True, sample_rate=1.0),
    )

    session = HeaderSession(
        builder=_builder(),
        config=config,
        client_options={"transport": transport},
        telemetry_sinks=[collector],
        telemetry_random=lambda: 0.0,
    )
    try:
        response = session.request("GET", "https://example.com/data")
    finally:
        session.close()

    assert response.status_code == 200
    assert collector.events
    event = collector.events[0]
    assert event.event == "request.success"
    assert str(event.request_url) == "https://example.com/data"


async def test_async_session_emits_failure_event(anyio_backend):
    collector = Collector()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": True})

    transport = httpx.MockTransport(handler)
    config = HeaderEmulatorConfig(
        retry=RetryConfig(max_attempts=1, backoff_factor=0.1, jitter_seconds=0.0),
        throttle=ThrottleConfig(enabled=False),
        telemetry=TelemetryConfig(enabled=True, sample_rate=1.0),
    )

    async with AsyncHeaderSession(
        builder=_builder(),
        config=config,
        client_options={"transport": transport},
        sleep=lambda _: anyio.sleep(0),
        telemetry_sinks=[collector],
        telemetry_random=lambda: 0.0,
    ) as session:
        try:
            await session.request("GET", "https://example.com/data")
        except RuntimeError:
            pass

    assert any(evt.event == "request.final_failure" for evt in collector.events)


def test_rotator_emits_cooldown_event():
    builder = _builder()
    telemetry_cfg = TelemetryConfig(enabled=True, sample_rate=1.0)
    config = HeaderEmulatorConfig(
        rotation_strategy=RotationStrategy.ROUND_ROBIN,
        cooldown=CooldownConfig(policy="cooldown", cooldown_seconds=60, failure_threshold=1),
        telemetry=telemetry_cfg,
    )
    rotator = HeaderRotator(builder=builder, config=config, persistence=MemoryPersistenceAdapter())
    sink = InMemoryTelemetrySink()
    publisher = TelemetryPublisher(telemetry_cfg, random_fn=lambda: 0.0)
    publisher.subscribe(sink)
    rotator.attach_telemetry(publisher)

    profile_id = rotator.next_request().profile_id
    rotator.record_failure(profile_id)

    assert any(event.event == "profile.cooldown" for event in sink.events)


def test_proxy_manager_emits_failure_event():
    telemetry_cfg = TelemetryConfig(enabled=True, sample_rate=1.0)
    publisher = TelemetryPublisher(telemetry_cfg, random_fn=lambda: 0.0)
    sink = InMemoryTelemetrySink()
    publisher.subscribe(sink)

    provider = ProxyProvider(
        [ProxyConfig(scheme=ProxyScheme.HTTP, host="127.0.0.1", port=8000)]
    )
    config = ProxyPoolConfig(preload=False)
    manager = ProxyManager(provider, config, telemetry=publisher)

    proxy = manager.select()
    manager.mark_failure(proxy)

    assert any(event.event == "proxy.failure" for event in sink.events)
