"""Public package interface for header_emulator."""

from .builder import FETCH_INTENT_API, FETCH_INTENT_DOCUMENT, HeaderBuilder
from .config import HeaderEmulatorConfig
from .providers import LocaleProvider, ProxyProvider, UserAgentProvider
from .persistence import MemoryPersistenceAdapter, PersistenceAdapter
from .external_sources import proxies_from_proxyscrape, user_agents_from_intoli
from .emulator import HeaderEmulator
from .middleware import Middleware, MiddlewareManager
from .proxy_tools import healthcheck_proxies
from .rotator import HeaderRotator
from .session import AsyncHeaderSession, HeaderSession
from .profile_loader import load_profiles
from .requests_support import requests_request
from .types import (
    HeaderProfile,
    RotationStrategy,
    StickySessionKey,
)

__all__ = [
    "FETCH_INTENT_API",
    "FETCH_INTENT_DOCUMENT",
    "HeaderBuilder",
    "HeaderEmulatorConfig",
    "HeaderProfile",
    "HeaderRotator",
    "HeaderSession",
    "AsyncHeaderSession",
    "LocaleProvider",
    "ProxyProvider",
    "RotationStrategy",
    "StickySessionKey",
    "UserAgentProvider",
    "PersistenceAdapter",
    "MemoryPersistenceAdapter",
    "Middleware",
    "MiddlewareManager",
    "HeaderEmulator",
    "healthcheck_proxies",
    "load_profiles",
    "requests_request",
    "proxies_from_proxyscrape",
    "user_agents_from_intoli",
]
