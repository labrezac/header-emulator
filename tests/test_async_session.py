import httpx
import pytest
import anyio

from header_emulator.builder import HeaderBuilder
from header_emulator.config import HeaderEmulatorConfig, RetryConfig, ThrottleConfig
from header_emulator.providers.locales import LocaleProvider
from header_emulator.providers.user_agents import UserAgentProvider, UserAgentRecord
from header_emulator.middleware import Middleware
from header_emulator.session import AsyncHeaderSession
from header_emulator.types import LocaleProfile, RotationStrategy


def _record(identifier: str, ua: str, weight: float = 1.0) -> UserAgentRecord:
    return UserAgentRecord(
        id=identifier,
        family="Chrome",
        version="120.0",
        device="desktop",
        os="Windows 11",
        mobile=False,
        touch=False,
        original=ua,
        weight=weight,
        accept_header="text/html",
        accept_language_hint="en-US,en;q=0.9",
    )


def _builder(records: list[UserAgentRecord]) -> HeaderBuilder:
    ua_provider = UserAgentProvider(records)
    locale_provider = LocaleProvider([LocaleProfile(language="en-US,en;q=0.9", country="US")])
    return HeaderBuilder(
        user_agents=ua_provider,
        locales=locale_provider,
        referers=["https://example.com/"],
    )


@pytest.mark.anyio
async def test_async_session_applies_rotated_headers():
    captured: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    builder = _builder([_record("alpha", "UA-ALPHA")])
    config = HeaderEmulatorConfig(
        retry=RetryConfig(max_attempts=1, backoff_factor=0.01, jitter_seconds=0.0),
        throttle=ThrottleConfig(enabled=False),
    )

    async with AsyncHeaderSession(
        builder=builder,
        config=config,
        client_options={"transport": transport},
        sleep=lambda _: anyio.sleep(0),
    ) as session:
        response = await session.request("GET", "https://example.com/data")

    assert response.status_code == 200
    assert len(captured) == 1
    request = captured[0]
    assert request.headers["User-Agent"] == "UA-ALPHA"
    assert request.headers["Referer"] == "https://example.com/"


@pytest.mark.anyio
async def test_async_session_retries_on_retryable_status():
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.headers["User-Agent"])
        if len(calls) == 1:
            return httpx.Response(403, text="forbidden")
        return httpx.Response(200, text="ok")

    transport = httpx.MockTransport(handler)
    builder = _builder([
        _record("alpha", "UA-ALPHA", weight=0.5),
        _record("beta", "UA-BETA", weight=0.5),
    ])
    config = HeaderEmulatorConfig(
        rotation_strategy=RotationStrategy.ROUND_ROBIN,
        retry=RetryConfig(max_attempts=2, backoff_factor=0.01, jitter_seconds=0.0),
        throttle=ThrottleConfig(enabled=False),
    )

    async with AsyncHeaderSession(
        builder=builder,
        config=config,
        client_options={"transport": transport},
        sleep=lambda _: anyio.sleep(0),
    ) as session:
        response = await session.request("GET", "https://example.com/data")

    assert response.status_code == 200
    assert len(calls) == 2
    assert calls[0] != calls[1]


class CaptureMiddleware(Middleware):
    def __init__(self) -> None:
        self.before_profiles: list[str] = []
        self.after_statuses: list[int] = []

    def before_send(self, request, profile) -> None:
        request.headers["X-Middleware"] = "1"
        self.before_profiles.append(profile.id)

    def after_response(self, request, response) -> None:
        self.after_statuses.append(response.status_code)


@pytest.mark.anyio
async def test_async_middleware_invocation():
    middleware = CaptureMiddleware()

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Middleware"] == "1"
        return httpx.Response(200, text="ok")

    transport = httpx.MockTransport(handler)
    builder = _builder([_record("alpha", "UA-ALPHA")])
    config = HeaderEmulatorConfig(
        retry=RetryConfig(max_attempts=1, backoff_factor=0.01, jitter_seconds=0.0),
        throttle=ThrottleConfig(enabled=False),
    )

    async with AsyncHeaderSession(
        builder=builder,
        config=config,
        client_options={"transport": transport},
        middlewares=[middleware],
    ) as session:
        await session.request("GET", "https://example.com/data")

    assert middleware.before_profiles == ["alpha"]
    assert middleware.after_statuses == [200]
