"""Telemetry publishing utilities."""

from __future__ import annotations

import logging
import random
from contextlib import contextmanager
from typing import Callable, Iterable, List, Optional, Protocol

from .config import TelemetryConfig
from .types import TelemetryEvent

LOGGER = logging.getLogger(__name__)


class TelemetrySink(Protocol):
    """Sink that handles telemetry events."""

    def handle(self, event: TelemetryEvent) -> None:  # pragma: no cover - protocol
        ...


class TelemetryPublisher:
    """Publish telemetry events to registered sinks respecting config sample rate."""

    def __init__(
        self,
        config: TelemetryConfig,
        *,
        random_fn: Callable[[], float] = random.random,
    ) -> None:
        self.config = config
        self._random = random_fn
        self._sinks: List[TelemetrySink] = []

    def subscribe(self, sink: TelemetrySink) -> None:
        self._sinks.append(sink)

    def unsubscribe(self, sink: TelemetrySink) -> None:
        try:
            self._sinks.remove(sink)
        except ValueError:  # pragma: no cover - defensive
            pass

    @contextmanager
    def subscribed(self, sink: TelemetrySink):
        self.subscribe(sink)
        try:
            yield sink
        finally:
            self.unsubscribe(sink)

    def emit(self, event: TelemetryEvent) -> None:
        if not self.config.enabled:
            return
        if self._random() > self.config.sample_rate:
            return
        for sink in list(self._sinks):
            try:
                sink.handle(event)
            except Exception:  # pragma: no cover - defensive logging
                LOGGER.exception("Telemetry sink %s failed", sink)


class LoggingTelemetrySink:
    """Simple sink that logs events with the module logger."""

    def __init__(self, level: int = logging.INFO) -> None:
        self.level = level

    def handle(self, event: TelemetryEvent) -> None:
        LOGGER.log(self.level, "Telemetry event %s", event.model_dump())


class InMemoryTelemetrySink:
    """Collects telemetry events in memory for diagnostics or testing."""

    def __init__(self) -> None:
        self.events: list[TelemetryEvent] = []

    def handle(self, event: TelemetryEvent) -> None:
        self.events.append(event)


__all__ = [
    "TelemetryPublisher",
    "TelemetrySink",
    "LoggingTelemetrySink",
    "InMemoryTelemetrySink",
]


__all__ = ["TelemetryPublisher", "TelemetrySink", "LoggingTelemetrySink"]
