# Usage

## Quick Start

```python
from header_emulator import AsyncHeaderSession, HeaderEmulatorConfig

config = HeaderEmulatorConfig()

async def fetch(url: str) -> str:
    async with AsyncHeaderSession(config=config) as session:
        response = await session.request("GET", url)
        response.raise_for_status()
        return response.text
```

For synchronous code use `HeaderSession` instead of `AsyncHeaderSession`:

```python
from header_emulator import HeaderSession

with HeaderSession() as session:
    response = session.request("GET", "https://example.com")
    response.raise_for_status()
```

Both session types apply the rotation strategies, proxy policies, and throttling defined in your `HeaderEmulatorConfig`.

## Telemetry

You can subscribe to structured telemetry events to monitor retries, proxy health, and cooldown outcomes.

```python
from header_emulator import (
    HeaderSession,
    HeaderEmulatorConfig,
    LoggingTelemetrySink,
    TelemetryPublisher,
)

config = HeaderEmulatorConfig(telemetry={"enabled": True, "sample_rate": 1.0})
sink = LoggingTelemetrySink()

with HeaderSession(config=config, telemetry_sinks=[sink]) as session:
    response = session.request("GET", "https://example.com")
    response.raise_for_status()

# emitted events include request.success/retry/error as well as proxy.cooldown and profile.cooldown
```

For programmatic access, use `InMemoryTelemetrySink` to collect events and feed them into your metrics pipeline.

## Persistence Backends

Sticky sessions, proxies, and cooldown state can be shared across processes using different adapters:

- `MemoryPersistenceAdapter` (default): in-process only.
- `SQLitePersistenceAdapter`: lightweight, file-based persistence for a single host.
- `RedisPersistenceAdapter`: distributed persistence when multiple workers need to share state. Requires `redis-py`.

Select an adapter via configuration:

```python
from header_emulator import HeaderEmulatorConfig, RedisPersistenceAdapter

config = HeaderEmulatorConfig()
adapter = RedisPersistenceAdapter("redis://localhost:6379/0")

session = HeaderSession(config=config, persistence=adapter)

## Middleware

You can inject middleware to tweak headers or inspect responses before they are returned:

```python
from header_emulator import HeaderSession, Middleware

class AuthMiddleware:
    def before_send(self, request, profile):
        request.headers["Authorization"] = "Bearer ..."

    def after_response(self, request, response):
        if response.status_code == 401:
            # trigger refresh logic
            pass

with HeaderSession(middlewares=[AuthMiddleware()]) as session:
    session.request("GET", "https://example.com/api")
```
```
