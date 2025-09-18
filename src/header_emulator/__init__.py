"""Public package interface for header_emulator."""

from .builder import FETCH_INTENT_API, FETCH_INTENT_DOCUMENT, HeaderBuilder
from .config import HeaderEmulatorConfig
from .providers import LocaleProvider, ProxyProvider, UserAgentProvider
from .persistence import MemoryPersistenceAdapter, PersistenceAdapter, SQLitePersistenceAdapter
from .emulator import HeaderEmulator
from .middleware import Middleware, MiddlewareManager
from .rotator import HeaderRotator
from .session import AsyncHeaderSession, HeaderSession
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
    "SQLitePersistenceAdapter",
    "Middleware",
    "MiddlewareManager",
    "HeaderEmulator",
]
