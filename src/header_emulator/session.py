"""High-level HTTP client that applies header rotation automatically."""

from __future__ import annotations

import random
import time
from contextlib import AbstractContextManager
from typing import Any, Awaitable, Callable, Iterable, Mapping, MutableMapping, Optional

import anyio
import httpx

from .builder import FETCH_INTENT_DOCUMENT, HeaderBuilder
from .config import HeaderEmulatorConfig
from .middleware import Middleware, MiddlewareManager
from .persistence import PersistenceAdapter
from .rotator import HeaderRotator
from .telemetry import TelemetryPublisher, TelemetrySink
from .throttle import ThrottleController
from .types import (
    EmulatedRequest,
    LocaleProfile,
    ProxyConfig,
    RotationStrategy,
    StickySessionKey,
    TelemetryEvent,
)

RETRYABLE_STATUS_CODES = {403, 407, 408, 425, 429, 500, 502, 503, 504}


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0


class _ProxyTrackingMixin:
    builder: HeaderBuilder
    config: HeaderEmulatorConfig
    _telemetry: TelemetryPublisher

    def _mark_proxy_success(self, proxy: Optional[ProxyConfig]) -> None:
        manager = self.builder.proxy_manager
        if manager is not None and proxy is not None:
            manager.mark_success(proxy)

    def _mark_proxy_failure(self, proxy: Optional[ProxyConfig]) -> None:
        manager = self.builder.proxy_manager
        if manager is not None and proxy is not None:
            manager.mark_failure(proxy)

    def _emit_telemetry(
        self,
        event_name: str,
        emulated: EmulatedRequest,
        *,
        url: str,
        method: str,
        attempt: int,
        elapsed_ms: Optional[float] = None,
        response: Optional[httpx.Response] = None,
        error: Optional[Exception] = None,
    ) -> None:
        payload: dict[str, object] = {
            "method": method,
            "attempt": attempt,
        }
        if response is not None:
            payload["status_code"] = response.status_code
        if error is not None:
            payload["error"] = repr(error)
        if elapsed_ms is not None:
            payload["elapsed_ms"] = elapsed_ms
        if self.config.telemetry.include_headers:
            payload["headers"] = dict(emulated.headers)
        event = TelemetryEvent(
            event=event_name,
            payload=payload,
            request_url=url,
            proxy=emulated.proxy.url if emulated.proxy else None,
            profile_id=emulated.profile_id,
            status_code=response.status_code if response is not None else None,
            elapsed_ms=int(elapsed_ms) if elapsed_ms is not None else None,
        )
        self._telemetry.emit(event)


class HeaderSession(_ProxyTrackingMixin, AbstractContextManager):
    """Synchronous HTTP client that rotates headers and proxies per request."""

    def __init__(
        self,
        *,
        rotator: Optional[HeaderRotator] = None,
        persistence: Optional[PersistenceAdapter] = None,
        builder: Optional[HeaderBuilder] = None,
        config: Optional[HeaderEmulatorConfig] = None,
        client_options: Optional[dict[str, Any]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        telemetry_sinks: Optional[Iterable[TelemetrySink]] = None,
        telemetry_random: Optional[Callable[[], float]] = None,
        backoff_random: Optional[Callable[[], float]] = None,
        middlewares: Optional[Iterable[Middleware]] = None,
    ) -> None:
        base_builder = builder or HeaderBuilder()
        if rotator is None:
            rotator = HeaderRotator(builder=base_builder, config=config, persistence=persistence)
        self.rotator = rotator
        self.config = rotator.config
        self.builder = rotator.builder
        self._client_options = dict(client_options or {})
        self._default_client = httpx.Client(**self._client_options)
        self._proxy_clients: dict[str, httpx.Client] = {}
        self._sleep = sleep or time.sleep
        self._middleware = MiddlewareManager(list(middlewares or []))
        self._telemetry = TelemetryPublisher(
            self.config.telemetry,
            random_fn=telemetry_random or random.random,
        )
        for sink in telemetry_sinks or []:
            self._telemetry.subscribe(sink)
        self._throttle = ThrottleController(
            self.config.retry,
            self.config.throttle,
            random_fn=backoff_random,
        )
        self.rotator.attach_telemetry(self._telemetry)
        proxy_manager = self.builder.proxy_manager
        if proxy_manager is not None:
            proxy_manager.attach_telemetry(self._telemetry)

    # ------------------------------------------------------------------
    # Context management
    # ------------------------------------------------------------------
    def close(self) -> None:
        self._default_client.close()
        for client in self._proxy_clients.values():
            client.close()
        self._proxy_clients.clear()

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.close()

    # ------------------------------------------------------------------
    # Public request API
    # ------------------------------------------------------------------
    def request(
        self,
        method: str,
        url: str,
        *,
        strategy: Optional[RotationStrategy] = None,
        sticky_key: StickySessionKey | str | None = None,
        profile_id: Optional[str] = None,
        locale: Optional[LocaleProfile] = None,
        intent: str = FETCH_INTENT_DOCUMENT,
        referer: Optional[str] = None,
        with_proxy: Optional[bool] = None,
        headers: Optional[Mapping[str, str]] = None,
        cookies: Optional[MutableMapping[str, str]] = None,
        **request_kwargs: Any,
    ) -> httpx.Response:
        """Send a request using rotated headers and proxies."""

        attempts = 0
        last_exc: Optional[Exception] = None
        last_emulated: Optional[EmulatedRequest] = None
        while attempts < self.config.retry.max_attempts:
            attempts += 1
            emulated = self.rotator.next_request(
                strategy=strategy,
                sticky_key=sticky_key,
                profile_id=profile_id,
                locale=locale,
                intent=intent,
                referer=referer,
                cookies=cookies,
                headers_override=headers,
                with_proxy=with_proxy,
            )
            last_emulated = emulated
            if emulated.profile is not None:
                self._middleware.before_send(emulated, emulated.profile)
            start = time.perf_counter()
            try:
                response = self._send_request(method, url, emulated, **request_kwargs)
            except httpx.HTTPError as exc:
                last_exc = exc
                self._mark_proxy_failure(emulated.proxy)
                self.rotator.record_failure(emulated.profile_id or "", sticky_key=sticky_key)
                self._emit_telemetry(
                    "request.error",
                    emulated,
                    url=url,
                    method=method,
                    attempt=attempts,
                    error=exc,
                    elapsed_ms=_elapsed_ms(start),
                )
                delay = self._throttle.backoff_delay(attempts)
                if delay > 0:
                    self._sleep(delay)
                continue

            if self._should_retry(response):
                if emulated.profile is not None:
                    self._middleware.after_response(emulated, response)
                self._mark_proxy_failure(emulated.proxy)
                self.rotator.record_failure(emulated.profile_id or "", sticky_key=sticky_key)
                self._emit_telemetry(
                    "request.retry",
                    emulated,
                    url=url,
                    method=method,
                    attempt=attempts,
                    response=response,
                    elapsed_ms=_elapsed_ms(start),
                )
                delay = self._throttle.backoff_delay(attempts, response)
                if delay > 0:
                    self._sleep(delay)
                continue

            self.rotator.record_success(emulated.profile_id or "")
            self._mark_proxy_success(emulated.proxy)
            self._apply_throttle(response)
            self._emit_telemetry(
                "request.success",
                emulated,
                url=url,
                method=method,
                attempt=attempts,
                response=response,
                elapsed_ms=_elapsed_ms(start),
            )
            if emulated.profile is not None:
                self._middleware.after_response(emulated, response)
            return response

        # Exhausted attempts, raise last exception or a HTTP status error
        if last_exc is not None:
            if last_emulated is not None:
                self._emit_telemetry(
                    "request.final_failure",
                    last_emulated,
                    url=url,
                    method=method,
                    attempt=attempts,
                    error=last_exc,
                )
            raise last_exc
        if last_emulated is not None:
            self._emit_telemetry(
                "request.final_failure",
                last_emulated,
                url=url,
                method=method,
                attempt=attempts,
            )
        raise RuntimeError("Exceeded maximum retry attempts without success")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _send_request(
        self,
        method: str,
        url: str,
        emulated: EmulatedRequest,
        **request_kwargs: Any,
    ) -> httpx.Response:
        headers = dict(emulated.headers)
        cookies = dict(emulated.cookies)
        cookies_param = cookies or None
        proxy_url = emulated.proxy.url if emulated.proxy else None
        client = self._get_client(proxy_url)
        return client.request(method, url, headers=headers, cookies=cookies_param, **request_kwargs)

    def _get_client(self, proxy_url: Optional[str]) -> httpx.Client:
        if not proxy_url:
            return self._default_client
        if proxy_url not in self._proxy_clients:
            options = dict(self._client_options)
            options.update({"proxies": proxy_url})
            self._proxy_clients[proxy_url] = httpx.Client(**options)
        return self._proxy_clients[proxy_url]

    def _should_retry(self, response: httpx.Response) -> bool:
        if response.status_code in RETRYABLE_STATUS_CODES:
            return True
        if 500 <= response.status_code < 600:
            return True
        return False

    def _apply_throttle(self, response: httpx.Response) -> None:
        delay = self._throttle.throttle_delay(response)
        if delay > 0:
            self._sleep(delay)


__all__ = ["HeaderSession", "AsyncHeaderSession"]


class AsyncHeaderSession(_ProxyTrackingMixin):
    """Asynchronous HTTP client that rotates headers and proxies per request."""

    def __init__(
        self,
        *,
        rotator: Optional[HeaderRotator] = None,
        persistence: Optional[PersistenceAdapter] = None,
        builder: Optional[HeaderBuilder] = None,
        config: Optional[HeaderEmulatorConfig] = None,
        client_options: Optional[dict[str, Any]] = None,
        sleep: Optional[Callable[[float], Awaitable[None]]] = None,
        telemetry_sinks: Optional[Iterable[TelemetrySink]] = None,
        telemetry_random: Optional[Callable[[], float]] = None,
        backoff_random: Optional[Callable[[], float]] = None,
        middlewares: Optional[Iterable[Middleware]] = None,
    ) -> None:
        base_builder = builder or HeaderBuilder()
        if rotator is None:
            rotator = HeaderRotator(builder=base_builder, config=config, persistence=persistence)
        self.rotator = rotator
        self.config = rotator.config
        self.builder = rotator.builder
        self._client_options = dict(client_options or {})
        self._default_client = httpx.AsyncClient(**self._client_options)
        self._proxy_clients: dict[str, httpx.AsyncClient] = {}
        self._sleep = sleep or anyio.sleep
        self._middleware = MiddlewareManager(list(middlewares or []))
        self._telemetry = TelemetryPublisher(
            self.config.telemetry,
            random_fn=telemetry_random or random.random,
        )
        for sink in telemetry_sinks or []:
            self._telemetry.subscribe(sink)
        self._throttle = ThrottleController(
            self.config.retry,
            self.config.throttle,
            random_fn=backoff_random,
        )
        self.rotator.attach_telemetry(self._telemetry)
        proxy_manager = self.builder.proxy_manager
        if proxy_manager is not None:
            proxy_manager.attach_telemetry(self._telemetry)

    async def aclose(self) -> None:
        await self._default_client.aclose()
        for client in self._proxy_clients.values():
            await client.aclose()
        self._proxy_clients.clear()

    async def __aenter__(self) -> "AsyncHeaderSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def request(
        self,
        method: str,
        url: str,
        *,
        strategy: Optional[RotationStrategy] = None,
        sticky_key: StickySessionKey | str | None = None,
        profile_id: Optional[str] = None,
        locale: Optional[LocaleProfile] = None,
        intent: str = FETCH_INTENT_DOCUMENT,
        referer: Optional[str] = None,
        with_proxy: Optional[bool] = None,
        headers: Optional[Mapping[str, str]] = None,
        cookies: Optional[MutableMapping[str, str]] = None,
        **request_kwargs: Any,
    ) -> httpx.Response:
        attempts = 0
        last_exc: Optional[Exception] = None
        last_emulated: Optional[EmulatedRequest] = None
        while attempts < self.config.retry.max_attempts:
            attempts += 1
            emulated = self.rotator.next_request(
                strategy=strategy,
                sticky_key=sticky_key,
                profile_id=profile_id,
                locale=locale,
                intent=intent,
                referer=referer,
                cookies=cookies,
                headers_override=headers,
                with_proxy=with_proxy,
            )
            last_emulated = emulated
            if emulated.profile is not None:
                self._middleware.before_send(emulated, emulated.profile)
            start = time.perf_counter()
            try:
                response = await self._send_request(method, url, emulated, **request_kwargs)
            except httpx.HTTPError as exc:
                last_exc = exc
                self._mark_proxy_failure(emulated.proxy)
                self.rotator.record_failure(emulated.profile_id or "", sticky_key=sticky_key)
                self._emit_telemetry(
                    "request.error",
                    emulated,
                    url=url,
                    method=method,
                    attempt=attempts,
                    error=exc,
                    elapsed_ms=_elapsed_ms(start),
                )
                delay = self._throttle.backoff_delay(attempts)
                if delay > 0:
                    await self._sleep(delay)
                continue

            if self._should_retry(response):
                if emulated.profile is not None:
                    self._middleware.after_response(emulated, response)
                self._mark_proxy_failure(emulated.proxy)
                self.rotator.record_failure(emulated.profile_id or "", sticky_key=sticky_key)
                self._emit_telemetry(
                    "request.retry",
                    emulated,
                    url=url,
                    method=method,
                    attempt=attempts,
                    response=response,
                    elapsed_ms=_elapsed_ms(start),
                )
                delay = self._throttle.backoff_delay(attempts, response)
                if delay > 0:
                    await self._sleep(delay)
                continue

            self.rotator.record_success(emulated.profile_id or "")
            self._mark_proxy_success(emulated.proxy)
            await self._apply_throttle(response)
            self._emit_telemetry(
                "request.success",
                emulated,
                url=url,
                method=method,
                attempt=attempts,
                response=response,
                elapsed_ms=_elapsed_ms(start),
            )
            if emulated.profile is not None:
                self._middleware.after_response(emulated, response)
            return response

        if last_exc is not None:
            if last_emulated is not None:
                self._emit_telemetry(
                    "request.final_failure",
                    last_emulated,
                    url=url,
                    method=method,
                    attempt=attempts,
                    error=last_exc,
                )
            raise last_exc
        if last_emulated is not None:
            self._emit_telemetry(
                "request.final_failure",
                last_emulated,
                url=url,
                method=method,
                attempt=attempts,
            )
        raise RuntimeError("Exceeded maximum retry attempts without success")

    async def _send_request(
        self,
        method: str,
        url: str,
        emulated: EmulatedRequest,
        **request_kwargs: Any,
    ) -> httpx.Response:
        headers = dict(emulated.headers)
        cookies = dict(emulated.cookies)
        cookies_param = cookies or None
        proxy_url = emulated.proxy.url if emulated.proxy else None
        client = await self._get_client(proxy_url)
        return await client.request(
            method,
            url,
            headers=headers,
            cookies=cookies_param,
            **request_kwargs,
        )

    async def _get_client(self, proxy_url: Optional[str]) -> httpx.AsyncClient:
        if not proxy_url:
            return self._default_client
        if proxy_url not in self._proxy_clients:
            options = dict(self._client_options)
            options.update({"proxies": proxy_url})
            self._proxy_clients[proxy_url] = httpx.AsyncClient(**options)
        return self._proxy_clients[proxy_url]

    def _should_retry(self, response: httpx.Response) -> bool:
        if response.status_code in RETRYABLE_STATUS_CODES:
            return True
        if 500 <= response.status_code < 600:
            return True
        return False

    async def _apply_throttle(self, response: httpx.Response) -> None:
        delay = self._throttle.throttle_delay(response)
        if delay > 0:
            await self._sleep(delay)


__all__ = ["HeaderSession", "AsyncHeaderSession"]
