"""Adaptive throttle and backoff management."""

from __future__ import annotations

import random
from typing import Optional

import httpx

from .config import RetryConfig, ThrottleConfig


class ThrottleController:
    """Computes retry backoff and steady-state throttle delays."""

    def __init__(
        self,
        retry: RetryConfig,
        throttle: ThrottleConfig,
        *,
        random_fn: Optional[callable] = None,
    ) -> None:
        self._retry = retry
        self._throttle = throttle
        self._random = random_fn or random.random

    def backoff_delay(self, attempt: int, response: Optional[httpx.Response] = None) -> float:
        """Return delay in seconds before the next retry."""

        retry = self._retry
        throttle = self._throttle

        delay = retry.backoff_factor * (2 ** max(0, attempt - 1))
        if retry.jitter_seconds:
            delay += self._random() * retry.jitter_seconds

        if response is not None and throttle.enabled and throttle.use_server_hints:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    delay = max(delay, float(retry_after))
                except ValueError:
                    pass

        if throttle.enabled:
            delay = min(delay, throttle.max_delay_seconds)
        return delay

    def throttle_delay(self, response: Optional[httpx.Response] = None) -> float:
        """Return steady-state post-response delay."""

        throttle = self._throttle
        if not throttle.enabled:
            return 0.0

        delay = min(throttle.base_delay_seconds, throttle.max_delay_seconds)
        if throttle.use_server_hints and response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    delay = max(delay, float(retry_after))
                except ValueError:
                    pass
        return delay


__all__ = ["ThrottleController"]
