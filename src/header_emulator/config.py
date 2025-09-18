"""Configuration models for the header emulator."""

from __future__ import annotations

from datetime import timedelta
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, PositiveFloat, PositiveInt, ValidationInfo, field_validator

from .types import FailurePolicy, RotationStrategy


class RetryConfig(BaseModel):
    """Retry configuration influencing throttle behavior."""

    max_attempts: PositiveInt = Field(
        default=3,
        description="Maximum retry attempts per request before giving up.",
    )
    backoff_factor: PositiveFloat = Field(
        default=0.5,
        description="Base for exponential backoff timing (seconds).",
    )
    jitter_seconds: float = Field(
        default=0.3,
        ge=0.0,
        description="Random jitter added to backoff to avoid lockstep retries.",
    )


class CooldownConfig(BaseModel):
    """Controls how failing proxies or profiles are cooled down."""

    policy: FailurePolicy = FailurePolicy.COOLDOWN
    cooldown_seconds: int = Field(
        default=300,
        ge=0,
        description="How long to wait before reusing a cooled-down entry.",
    )
    failure_threshold: PositiveInt = Field(
        default=3,
        description="Number of consecutive failures before cooldown applies.",
    )


class StickySessionConfig(BaseModel):
    """Sticky session behavior for repeat callers."""

    enabled: bool = True
    ttl_seconds: int = Field(
        default=900,
        ge=60,
        description="Lifetime for sticky bindings between callers and profiles.",
    )
    max_pool_size: PositiveInt = Field(
        default=1000,
        description="Maximum number of sticky sessions that can be cached.",
    )


class ThrottleConfig(BaseModel):
    """Adaptive throttling to avoid rate-limits (see ZenRows guidance)."""

    enabled: bool = True
    base_delay_seconds: float = Field(default=0.0, ge=0.0)
    max_delay_seconds: float = Field(default=10.0, ge=0.0)
    use_server_hints: bool = Field(
        default=True,
        description="Adjust throttle based on Retry-After or rate-limit headers when present.",
    )

    @field_validator("max_delay_seconds")
    @classmethod
    def _validate_range(cls, value: float, info: ValidationInfo) -> float:
        base = info.data.get("base_delay_seconds", 0.0)
        if value < base:
            raise ValueError("max_delay_seconds cannot be smaller than base_delay_seconds")
        return value


class ProxyPoolConfig(BaseModel):
    """Configuration for managing the proxy pool."""

    enabled: bool = True
    healthcheck_url: Optional[str] = Field(
        default="https://httpbin.org/status/204",
        description="Endpoint used to verify proxy health before usage.",
    )
    healthcheck_timeout_seconds: PositiveFloat = Field(default=5.0)
    rotation_strategy: RotationStrategy = RotationStrategy.WEIGHTED
    failure_policy: FailurePolicy = FailurePolicy.COOLDOWN
    preload: bool = Field(
        default=True,
        description="Run a background healthcheck for proxies before accepting requests.",
    )
    failure_threshold: PositiveInt = Field(
        default=1,
        description="How many consecutive failures before applying the failure policy.",
    )
    cooldown_seconds: int = Field(
        default=60,
        ge=0,
        description="Cooldown duration applied when proxies fail and policy is cooldown.",
    )


class PersistenceBackend(str, Enum):
    """Supported persistence backends for sharing rotation state."""

    MEMORY = "memory"


class PersistenceConfig(BaseModel):
    """State persistence configuration."""

    backend: PersistenceBackend = PersistenceBackend.MEMORY
    dsn: Optional[str] = None
    namespace: str = Field(default="header_emulator")


class HeaderEmulatorConfig(BaseModel):
    """Top-level configuration object for the package."""

    rotation_strategy: RotationStrategy = RotationStrategy.RANDOM
    retry: RetryConfig = Field(default_factory=RetryConfig)
    cooldown: CooldownConfig = Field(default_factory=CooldownConfig)
    sticky: StickySessionConfig = Field(default_factory=StickySessionConfig)
    throttle: ThrottleConfig = Field(default_factory=ThrottleConfig)
    proxies: ProxyPoolConfig = Field(default_factory=ProxyPoolConfig)
    persistence: PersistenceConfig = Field(default_factory=PersistenceConfig)
    default_profile: Optional[str] = Field(
        default=None,
        description="Identifier of the default header profile to use when unspecified.",
    )

    def sticky_ttl(self) -> timedelta:
        """Return the sticky TTL as a timedelta for convenience."""

        return timedelta(seconds=self.sticky.ttl_seconds)


__all__ = [
    "CooldownConfig",
    "HeaderEmulatorConfig",
    "PersistenceBackend",
    "PersistenceConfig",
    "ProxyPoolConfig",
    "RetryConfig",
    "StickySessionConfig",
    "ThrottleConfig",
]
