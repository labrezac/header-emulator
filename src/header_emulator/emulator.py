"""High level facade for constructing header sessions."""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Iterable, Optional

from .builder import HeaderBuilder
from .config import HeaderEmulatorConfig
from .middleware import Middleware
from .persistence import MemoryPersistenceAdapter, PersistenceAdapter
from .providers import LocaleProvider, ProxyProvider, UserAgentProvider
from .proxy_manager import ProxyManager
from .rotator import HeaderRotator
from .session import AsyncHeaderSession, HeaderSession
from .types import EmulatedRequest, ProxyConfig
from .profile_loader import load_profiles


class HeaderEmulator(AbstractContextManager):
    """Bundle builder, rotator, and sessions behind a simple facade."""

    def __init__(
        self,
        *,
        config: Optional[HeaderEmulatorConfig] = None,
        user_agents: Optional[UserAgentProvider] = None,
        locales: Optional[LocaleProvider] = None,
        proxies: Optional[ProxyProvider] = None,
        persistence: Optional[PersistenceAdapter] = None,
        middlewares: Optional[Iterable[Middleware]] = None,
    ) -> None:
        self.config = config or HeaderEmulatorConfig()
        self.user_agents = user_agents or UserAgentProvider()
        self.locales = locales or LocaleProvider()
        self._middlewares = list(middlewares or [])
        self.persistence = persistence or MemoryPersistenceAdapter()
        proxy_manager = None
        if proxies is not None:
            proxy_manager = ProxyManager(proxies, self.config.proxies)
        self.builder = HeaderBuilder(
            user_agents=self.user_agents,
            locales=self.locales,
            proxies=None if proxy_manager else proxies,
            proxy_manager=proxy_manager,
        )
        self.rotator = HeaderRotator(
            builder=self.builder,
            config=self.config,
            persistence=self.persistence,
        )

    @classmethod
    def from_profile_file(
        cls,
        path: str | Path,
        *,
        config: Optional[HeaderEmulatorConfig] = None,
        proxies: Optional[ProxyProvider] = None,
        persistence: Optional[PersistenceAdapter] = None,
        middlewares: Optional[Iterable[Middleware]] = None,
    ) -> "HeaderEmulator":
        ua_provider, locale_provider = load_profiles(path)
        return cls(
            config=config,
            user_agents=ua_provider,
            locales=locale_provider,
            proxies=proxies,
            persistence=persistence,
            middlewares=middlewares,
        )

    # context manager interface closes default session if used
    def __enter__(self) -> "HeaderEmulator":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def session(self, **kwargs) -> HeaderSession:
        """Create a synchronous session using current configuration."""

        return HeaderSession(
            builder=self.builder,
            rotator=self.rotator,
            config=self.config,
            persistence=self.persistence,
            middlewares=[*self._middlewares, *kwargs.pop("middlewares", [])],
            **kwargs,
        )

    def async_session(self, **kwargs) -> AsyncHeaderSession:
        """Create an asynchronous session."""

        return AsyncHeaderSession(
            builder=self.builder,
            rotator=self.rotator,
            config=self.config,
            persistence=self.persistence,
            middlewares=[*self._middlewares, *kwargs.pop("middlewares", [])],
            **kwargs,
        )

    def next_request(self, **kwargs) -> "EmulatedRequest":
        """Return the next emulated request without sending it."""

        return self.rotator.next_request(**kwargs)

    def next_headers(
        self,
        *,
        with_proxy: bool = False,
        **kwargs,
    ) -> tuple[dict[str, str], Optional[ProxyConfig]]:
        """Convenience helper returning headers and optional proxy config."""

        request = self.next_request(with_proxy=with_proxy, **kwargs)
        return request.headers, request.proxy

    def request(
        self,
        method: str,
        url: str,
        *,
        session_kwargs: Optional[dict] = None,
        **request_kwargs,
    ):
        """Convenience helper that opens a temporary session to perform a request."""

        session_kwargs = session_kwargs or {}
        with self.session(**session_kwargs) as session:
            response = session.request(method, url, **request_kwargs)
            return response


__all__ = ["HeaderEmulator"]
