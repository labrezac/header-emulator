"""Middleware interface for request mutation."""

from __future__ import annotations

from typing import Any, Protocol

from .types import EmulatedRequest, HeaderProfile


class Middleware(Protocol):
    """Mutate request headers/cookies before sending and inspect responses."""

    def before_send(self, request: EmulatedRequest, profile: HeaderProfile) -> None:
        ...

    def after_response(self, request: EmulatedRequest, response: Any) -> None:
        ...


class MiddlewareManager:
    """Runs middleware in order for request/response lifecycle."""

    def __init__(self, middlewares: list[Middleware] | None = None) -> None:
        self._middlewares = list(middlewares or [])

    def add(self, middleware: Middleware) -> None:
        self._middlewares.append(middleware)

    def before_send(self, request: EmulatedRequest, profile: HeaderProfile) -> None:
        for middleware in self._middlewares:
            middleware.before_send(request, profile)

    def after_response(self, request: EmulatedRequest, response: Any) -> None:
        for middleware in reversed(self._middlewares):
            middleware.after_response(request, response)


__all__ = ["Middleware", "MiddlewareManager"]
