"""Rotation engine orchestrating header and proxy selection."""

from __future__ import annotations

import random
import time
from typing import Mapping, MutableMapping, Optional

from .builder import FETCH_INTENT_DOCUMENT, HeaderBuilder
from .config import HeaderEmulatorConfig, PersistenceBackend
from .persistence import MemoryPersistenceAdapter, PersistenceAdapter, SQLitePersistenceAdapter
from .utils import weighted_choice
from .telemetry import TelemetryPublisher
from .types import (
    EmulatedRequest,
    FailurePolicy,
    LocaleProfile,
    ProxyConfig,
    RotationStrategy,
    StickySessionKey,
)


class HeaderRotator:
    """High-level interface for producing rotated requests."""

    def __init__(
        self,
        builder: Optional[HeaderBuilder] = None,
        *,
        config: Optional[HeaderEmulatorConfig] = None,
        persistence: Optional[PersistenceAdapter] = None,
    ) -> None:
        self.builder = builder or HeaderBuilder()
        self.config = config or HeaderEmulatorConfig()
        self.persistence = persistence or self._create_persistence_adapter()
        self._telemetry: Optional[TelemetryPublisher] = None
        self._sticky_session_store = self.persistence.sticky_sessions()
        self._sticky_proxy_store = self.persistence.sticky_proxies()
        self._cooldown_store = self.persistence.cooldowns()
        self._profile_ids: list[str] = []
        self._cursor = 0
        self._profile_failures: dict[str, int] = {}
        self._evicted_profiles: set[str] = set()
        self.refresh_profiles()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh_profiles(self) -> None:
        """Re-snapshot provider data, e.g., after updating records."""

        records = self.builder.user_agents.all()
        if not records:
            raise ValueError("HeaderRotator requires at least one user-agent profile")
        self._profile_ids = [record.id for record in records]
        self._cursor %= len(self._profile_ids)

    def next_request(
        self,
        *,
        strategy: Optional[RotationStrategy] = None,
        sticky_key: StickySessionKey | str | None = None,
        profile_id: Optional[str] = None,
        locale: Optional[LocaleProfile] = None,
        intent: str = FETCH_INTENT_DOCUMENT,
        referer: Optional[str] = None,
        cookies: Optional[MutableMapping[str, str]] = None,
        headers_override: Optional[Mapping[str, str]] = None,
        with_proxy: Optional[bool] = None,
    ) -> EmulatedRequest:
        """Produce the next emulated request based on the rotation strategy."""

        strategy = strategy or self.config.rotation_strategy
        sticky_token = self._normalize_sticky_key(sticky_key)
        effective_with_proxy = self._resolve_proxy_flag(with_proxy)

        if profile_id is None:
            profile_id = self._select_profile(strategy=strategy, sticky_token=sticky_token)
        elif sticky_token and self.config.sticky.enabled:
            self._register_sticky_profile(sticky_token, profile_id)

        proxy_override = None
        if effective_with_proxy:
            proxy_override = self._resolve_sticky_proxy(sticky_token)

        request = self.builder.build_request(
            profile_id=profile_id,
            locale=locale,
            intent=intent,
            referer=referer,
            cookies=cookies,
            headers_override=headers_override,
            with_proxy=effective_with_proxy and proxy_override is None,
            proxy=proxy_override,
        )

        if effective_with_proxy:
            assigned_proxy = request.proxy
            if sticky_token and assigned_proxy is not None and self.config.sticky.enabled:
                self._register_sticky_proxy(sticky_token, assigned_proxy)

        if sticky_token and self.config.sticky.enabled:
            self._register_sticky_profile(sticky_token, request.profile_id or profile_id)

        return request

    def record_success(self, profile_id: str) -> None:
        """Reset failure counters after a successful call."""

        self._profile_failures.pop(profile_id, None)
        self._cooldown_store.remove(profile_id)

    def record_failure(
        self,
        profile_id: str,
        *,
        sticky_key: StickySessionKey | str | None = None,
    ) -> None:
        """Register a failure and apply the configured policy."""

        if sticky_key is not None:
            token = self._normalize_sticky_key(sticky_key)
            if token:
                self._sticky_session_store.delete(token)
                self._sticky_proxy_store.delete(token)

        policy = self.config.cooldown.policy
        if policy is FailurePolicy.RETAIN:
            return

        count = self._profile_failures.get(profile_id, 0) + 1
        threshold = self.config.cooldown.failure_threshold
        if count < threshold:
            self._profile_failures[profile_id] = count
            return

        self._profile_failures[profile_id] = 0
        if policy is FailurePolicy.COOLDOWN:
            expires = time.time() + self.config.cooldown.cooldown_seconds
            self._cooldown_store.set(profile_id, expires)
            self._emit_telemetry(
                "profile.cooldown",
                profile_id=profile_id,
                payload={"expires_at": expires},
            )
        elif policy is FailurePolicy.EVICT:
            self._evicted_profiles.add(profile_id)
            self._emit_telemetry("profile.evict", profile_id=profile_id)

    # ------------------------------------------------------------------
    # Selection helpers
    # ------------------------------------------------------------------
    def _select_profile(
        self,
        *,
        strategy: RotationStrategy,
        sticky_token: Optional[str],
    ) -> str:
        if sticky_token and self.config.sticky.enabled:
            sticky_profile = self._resolve_sticky_profile(sticky_token)
            if sticky_profile:
                return sticky_profile

        base_strategy = (
            RotationStrategy.WEIGHTED
            if strategy is RotationStrategy.STICKY
            else strategy
        )
        profile_id = self._choose_profile(base_strategy)
        if sticky_token and self.config.sticky.enabled:
            self._register_sticky_profile(sticky_token, profile_id)
        return profile_id

    def _choose_profile(self, strategy: RotationStrategy) -> str:
        blocked = self._blocked_profiles()
        records = [record for record in self.builder.user_agents.all() if record.id not in blocked]
        if not records:
            raise RuntimeError("No available header profiles to rotate")

        if strategy is RotationStrategy.ROUND_ROBIN:
            return self._next_round_robin(blocked)
        if strategy is RotationStrategy.WEIGHTED:
            weights = [record.weight for record in records]
            if not any(weight > 0 for weight in weights):
                return random.choice(records).id
            return weighted_choice(records, weights).id
        if strategy is RotationStrategy.RANDOM:
            return random.choice(records).id
        # default fallback
        return random.choice(records).id

    def _next_round_robin(self, blocked: set[str]) -> str:
        total = len(self._profile_ids)
        if total == 0:
            raise RuntimeError("HeaderRotator requires user-agent profiles")
        for _ in range(total):
            profile_id = self._profile_ids[self._cursor]
            self._cursor = (self._cursor + 1) % total
            if profile_id in blocked:
                continue
            return profile_id
        raise RuntimeError("All profiles are temporarily blocked")

    def _blocked_profiles(self) -> set[str]:
        blocked = set(self._evicted_profiles)
        now = time.time()
        # prune expired entries for stores that expose pruning
        self._cooldown_store.prune(now)
        for record in self.builder.user_agents.all():
            if self._cooldown_store.get(record.id) is not None:
                blocked.add(record.id)
        return blocked

    # ------------------------------------------------------------------
    # Sticky helpers
    # ------------------------------------------------------------------
    def _normalize_sticky_key(self, sticky_key: StickySessionKey | str | None) -> Optional[str]:
        if sticky_key is None:
            return None
        if isinstance(sticky_key, StickySessionKey):
            return sticky_key.model_dump_json()
        if isinstance(sticky_key, str):
            return sticky_key
        raise TypeError("sticky_key must be a StickySessionKey, string, or None")

    def _resolve_sticky_profile(self, token: str) -> Optional[str]:
        self._prune_sticky()
        return self._sticky_session_store.get(token)

    def _resolve_sticky_proxy(self, token: Optional[str]) -> Optional[ProxyConfig]:
        if not token or not self.config.sticky.enabled:
            return None
        self._prune_sticky()
        return self._sticky_proxy_store.get(token)

    def _register_sticky_profile(self, token: str, profile_id: str) -> None:
        if not self.config.sticky.enabled:
            return
        ttl = self.config.sticky.ttl_seconds
        self._sticky_session_store.set(token, profile_id, ttl)
        self._enforce_sticky_pool_limit()

    def _register_sticky_proxy(self, token: str, proxy: ProxyConfig) -> None:
        if not self.config.sticky.enabled:
            return
        ttl = self.config.sticky.ttl_seconds
        self._sticky_proxy_store.set(token, proxy, ttl)
        self._enforce_sticky_pool_limit()

    def _prune_sticky(self) -> None:
        self._sticky_session_store.prune()
        self._sticky_proxy_store.prune()

    def _enforce_sticky_pool_limit(self) -> None:
        limit = self.config.sticky.max_pool_size
        if limit <= 0:
            return
        # For store-backed implementations, pruning will handle TTL expiration.
        # No additional eviction strategy required at this layer.

    # ------------------------------------------------------------------
    # Cooldown helpers
    # ------------------------------------------------------------------
    def _prune_cooldowns(self) -> None:
        self._cooldown_store.prune(time.time())

    def _resolve_proxy_flag(self, requested: Optional[bool]) -> bool:
        if requested is not None:
            return requested
        return bool(self.builder.proxies and self.config.proxies.enabled)

    def _create_persistence_adapter(self) -> PersistenceAdapter:
        persistence_cfg = self.config.persistence
        if persistence_cfg.backend is PersistenceBackend.MEMORY:
            return MemoryPersistenceAdapter()
        if persistence_cfg.backend is PersistenceBackend.SQLITE:
            dsn = persistence_cfg.dsn or ":memory:"
            return SQLitePersistenceAdapter(dsn)
        raise NotImplementedError(f"Unsupported persistence backend: {persistence_cfg.backend}")

    def attach_telemetry(self, telemetry: Optional[TelemetryPublisher]) -> None:
        self._telemetry = telemetry

    def _emit_telemetry(self, event: str, *, profile_id: Optional[str] = None, payload: Optional[dict[str, object]] = None) -> None:
        if self._telemetry is None or not self.config.telemetry.enabled:
            return
        from .types import TelemetryEvent  # local import to avoid cycle

        event_obj = TelemetryEvent(
            event=event,
            payload=payload or {},
            profile_id=profile_id,
        )
        self._telemetry.emit(event_obj)


__all__ = ["HeaderRotator"]
