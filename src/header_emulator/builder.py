"""Utilities for constructing realistic header profiles and requests."""

from __future__ import annotations

import random
from typing import Iterable, Mapping, MutableMapping, Optional, TYPE_CHECKING

from .constants import (
    API_ACCEPT_HEADER,
    COMMON_REFERERS,
    DEFAULT_ACCEPT_ENCODINGS,
    SEC_FETCH_HEADERS_DOCUMENT,
    SEC_FETCH_HEADERS_XHR,
)
from .providers import LocaleProvider, ProxyProvider, UserAgentProvider
from .proxy_manager import ProxyManager
from .types import EmulatedRequest, HeaderProfile, LocaleProfile, ProxyConfig

FETCH_INTENT_DOCUMENT = "document"
FETCH_INTENT_API = "api"


class HeaderBuilder:
    """Compose headers, cookies, and proxies into emulated requests."""

    def __init__(
        self,
        *,
        user_agents: Optional[UserAgentProvider] = None,
        locales: Optional[LocaleProvider] = None,
        proxies: Optional[ProxyProvider] = None,
        proxy_manager: Optional[ProxyManager] = None,
        referers: Iterable[str] | None = None,
    ) -> None:
        self._user_agents = user_agents or UserAgentProvider()
        self._locales = locales or LocaleProvider()
        self._proxy_manager = proxy_manager
        self._proxies = proxies if proxy_manager is None else None
        self._referers = list(referers) if referers is not None else list(COMMON_REFERERS)
        self._accept_encoding = ", ".join(DEFAULT_ACCEPT_ENCODINGS)

    @property
    def user_agents(self) -> UserAgentProvider:
        return self._user_agents

    @property
    def locales(self) -> LocaleProvider:
        return self._locales

    @property
    def proxies(self) -> Optional[ProxyProvider]:
        return self._proxies

    @property
    def proxy_manager(self) -> Optional[ProxyManager]:
        return self._proxy_manager

    # ------------------------------------------------------------------
    # Profile helpers
    # ------------------------------------------------------------------
    def _resolve_locale(self, hint: Optional[str], provided: Optional[LocaleProfile]) -> LocaleProfile:
        if provided is not None:
            return provided
        if hint:
            primary = hint.split(";")[0]
            country = None
            if "-" in primary:
                _, country = primary.split("-", 1)
            return LocaleProfile(language=hint, country=country)
        return self._locales.random()

    def _apply_fetch_headers(self, profile: HeaderProfile, intent: str) -> None:
        if intent == FETCH_INTENT_API:
            profile.accept = API_ACCEPT_HEADER
            profile.upgrade_insecure_requests = None
            headers = SEC_FETCH_HEADERS_XHR
        else:
            headers = SEC_FETCH_HEADERS_DOCUMENT
        profile.sec_fetch_dest = headers.get("Sec-Fetch-Dest")
        profile.sec_fetch_mode = headers.get("Sec-Fetch-Mode")
        profile.sec_fetch_site = headers.get("Sec-Fetch-Site")
        if "Sec-Fetch-User" in headers:
            profile.additional.setdefault("Sec-Fetch-User", headers["Sec-Fetch-User"])

    def _maybe_assign_referer(self, profile: HeaderProfile, referer: Optional[str]) -> None:
        if referer:
            profile.referer = referer
            return
        if not self._referers:
            return
        profile.referer = random.choice(self._referers)

    def create_profile(
        self,
        *,
        profile_id: Optional[str] = None,
        locale: Optional[LocaleProfile] = None,
        intent: str = FETCH_INTENT_DOCUMENT,
        referer: Optional[str] = None,
    ) -> HeaderProfile:
        """Return a fresh :class:`HeaderProfile`.

        Parameters mirror ZenRows advice: a caller can target document navigation or
        API-style calls and optionally pin locale/referer selections.
        """

        if profile_id:
            record = self._user_agents.get(profile_id)
        else:
            record = self._user_agents.random()
        resolved_locale = self._resolve_locale(record.accept_language_hint, locale)
        profile = record.to_profile(resolved_locale)
        profile.accept_language = resolved_locale.language
        profile.accept_encoding = self._accept_encoding
        self._apply_fetch_headers(profile, intent)
        self._maybe_assign_referer(profile, referer)
        return profile

    # ------------------------------------------------------------------
    # Request composition
    # ------------------------------------------------------------------
    def _select_proxy(self) -> Optional[ProxyConfig]:
        if self._proxy_manager is not None:
            return self._proxy_manager.select()
        if not self._proxies:
            return None
        proxies = self._proxies.all()
        if not proxies:
            return None
        weights = [proxy.weight for proxy in proxies]
        return random.choices(proxies, weights=weights, k=1)[0]

    def build_request(
        self,
        *,
        profile: Optional[HeaderProfile] = None,
        profile_id: Optional[str] = None,
        locale: Optional[LocaleProfile] = None,
        intent: str = FETCH_INTENT_DOCUMENT,
        referer: Optional[str] = None,
        cookies: Optional[MutableMapping[str, str]] = None,
        headers_override: Optional[Mapping[str, str]] = None,
        with_proxy: bool = False,
        proxy: Optional[ProxyConfig] = None,
    ) -> EmulatedRequest:
        """Assemble an :class:`EmulatedRequest` ready for dispatch."""

        chosen_profile = profile or self.create_profile(
            profile_id=profile_id, locale=locale, intent=intent, referer=referer
        )
        header_map = chosen_profile.headers()
        if headers_override:
            header_map.update(headers_override)
        selected_proxy = proxy
        if selected_proxy is None and with_proxy:
            selected_proxy = self._select_proxy()
        return EmulatedRequest(
            headers=header_map,
            cookies=dict(cookies or {}),
            proxy=selected_proxy,
            profile_id=chosen_profile.id,
            profile=chosen_profile,
        )


__all__ = ["HeaderBuilder", "FETCH_INTENT_API", "FETCH_INTENT_DOCUMENT"]
