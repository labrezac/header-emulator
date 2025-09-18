"""Proxy pool management with health checks and failure policies."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional

import httpx

from .config import ProxyPoolConfig
from .providers import ProxyProvider
from .utils import weighted_choice
from .types import FailurePolicy, ProxyConfig, RotationStrategy
from .telemetry import TelemetryPublisher


@dataclass
class _ProxyState:
    proxy: ProxyConfig
    failures: int = 0
    cooldown_until: float = 0.0


class ProxyManager:
    """Manage proxy rotation, cooldown, and health checking."""

    def __init__(
        self,
        provider: ProxyProvider,
        config: ProxyPoolConfig,
        *,
        client_factory: Optional[Callable[[ProxyConfig], httpx.Client]] = None,
        time_fn: Callable[[], float] = time.monotonic,
        telemetry: Optional[TelemetryPublisher] = None,
    ) -> None:
        self.provider = provider
        self.config = config
        self._client_factory = client_factory or self._default_client_factory
        self._time_fn = time_fn
        self._states: Dict[str, _ProxyState] = {}
        self._order: List[str] = []
        self._cursor = 0
        self._telemetry = telemetry
        self.reload()
        if self.config.preload:
            self._preload_healthchecks()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def reload(self) -> None:
        proxies = self.provider.all()
        self._states = {proxy.url: _ProxyState(proxy=proxy) for proxy in proxies}
        self._order = [proxy.url for proxy in proxies]
        self._cursor = 0

    def select(self) -> ProxyConfig:
        available = self._available_states()
        if not available:
            raise RuntimeError("No proxies available")

        strategy = self.config.rotation_strategy
        if strategy is RotationStrategy.ROUND_ROBIN:
            return self._select_round_robin()
        if strategy is RotationStrategy.WEIGHTED:
            weights = [state.proxy.weight for state in available]
            chosen = weighted_choice(available, weights)
            return chosen.proxy
        if strategy is RotationStrategy.RANDOM:
            return random.choice(available).proxy
        return random.choice(available).proxy

    def mark_success(self, proxy: ProxyConfig) -> None:
        state = self._states.get(proxy.url)
        if state is None:
            return
        state.failures = 0
        state.cooldown_until = 0.0
        self._emit("proxy.success", proxy, payload={"failures": state.failures})

    def mark_failure(self, proxy: ProxyConfig) -> None:
        state = self._states.get(proxy.url)
        if state is None:
            return
        state.failures += 1
        self._emit("proxy.failure", proxy, payload={"failures": state.failures})
        if state.failures < self.config.failure_threshold:
            return
        state.failures = 0
        policy = self.config.failure_policy
        if policy is FailurePolicy.RETAIN:
            return
        if policy is FailurePolicy.COOLDOWN:
            state.cooldown_until = self._time_fn() + self.config.cooldown_seconds
            self._emit("proxy.cooldown", proxy, payload={"cooldown_until": state.cooldown_until})
            return
        if policy is FailurePolicy.EVICT:
            self._evict(proxy.url)
            self._emit("proxy.evict", proxy)

    def healthcheck(self, proxy: ProxyConfig) -> bool:
        if not self.config.healthcheck_url:
            return True
        client = self._client_factory(proxy)
        try:
            response = client.get(
                self.config.healthcheck_url,
                timeout=self.config.healthcheck_timeout_seconds,
            )
            ok = response.status_code < 400
            self._emit(
                "proxy.healthcheck",
                proxy,
                payload={"status_code": response.status_code, "ok": ok},
            )
            return ok
        except httpx.HTTPError:
            self._emit("proxy.healthcheck", proxy, payload={"ok": False, "error": "http_error"})
            return False
        finally:
            client.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _available_states(self) -> List[_ProxyState]:
        now = self._time_fn()
        return [state for state in self._states.values() if state.cooldown_until <= now]

    def _select_round_robin(self) -> ProxyConfig:
        total = len(self._order)
        if total == 0:
            raise RuntimeError("No proxies configured")
        for _ in range(total):
            url = self._order[self._cursor % total]
            self._cursor = (self._cursor + 1) % total
            state = self._states.get(url)
            if state and state.cooldown_until <= self._time_fn():
                return state.proxy
        raise RuntimeError("All proxies are cooling down")

    def _evict(self, url: str) -> None:
        self._states.pop(url, None)
        self._order = [item for item in self._order if item != url]

    def _preload_healthchecks(self) -> None:
        for url, state in list(self._states.items()):
            if not self.healthcheck(state.proxy):
                self._evict(url)
                self._emit("proxy.preload_evict", state.proxy)

    def _default_client_factory(self, proxy: ProxyConfig) -> httpx.Client:
        return httpx.Client(
            proxies=proxy.url,
            timeout=self.config.healthcheck_timeout_seconds,
        )

    def attach_telemetry(self, telemetry: Optional[TelemetryPublisher]) -> None:
        self._telemetry = telemetry

    def _emit(self, event: str, proxy: ProxyConfig, payload: Optional[dict[str, object]] = None) -> None:
        if self._telemetry is None or not self.config.enabled:
            return
        from .types import TelemetryEvent

        event_obj = TelemetryEvent(
            event=event,
            payload=payload or {},
            proxy=proxy.url,
        )
        self._telemetry.emit(event_obj)


__all__ = ["ProxyManager"]
