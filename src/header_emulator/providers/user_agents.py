"""User-Agent provider utilities.

Informed by ZenRows' recommendations we default to realistic desktop and mobile
user-agents while allowing consumers to replenish them from remote feeds.
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Iterable, Sequence

import httpx
from pydantic import BaseModel, Field, ValidationError

from ..constants import DESKTOP_ACCEPT_HEADER, MOBILE_ACCEPT_HEADER, SEC_CH_UA_BRANDS
from ..types import HeaderProfile, LocaleProfile, UserAgentMetadata

LOGGER = logging.getLogger(__name__)


class UserAgentRecord(UserAgentMetadata):
    """Extends metadata with weighting and default header hints."""

    id: str = Field(..., description="Stable identifier for the profile.")
    weight: float = Field(default=1.0, ge=0.0)
    accept_header: str = Field(...)
    accept_language_hint: str = Field(...)

    def to_profile(self, locale: LocaleProfile) -> HeaderProfile:
        """Convert the record into a concrete header profile."""

        sec_ch = SEC_CH_UA_BRANDS.get(self.id)
        platform_token = None
        if self.os:
            platform_token = self.os.split()[0]
        return HeaderProfile(
            id=self.id,
            user_agent=self,
            accept=self.accept_header,
            accept_language=locale.language,
            sec_ch_ua=sec_ch,
            sec_ch_ua_mobile="?1" if self.mobile else "?0",
            sec_ch_ua_platform=platform_token,
            additional={},
        )


def _builtin_user_agents() -> list[UserAgentRecord]:
    """Hard-coded UA dataset covering top browser share (per ZenRows)."""

    desktop_locale = LocaleProfile(language="en-US,en;q=0.9", country="US")
    mobile_locale = LocaleProfile(language="en-US,en;q=0.8", country="US")
    return [
        UserAgentRecord(
            id="desktop_chrome",
            family="Chrome",
            version="112.0.5615.138",
            device="desktop",
            os="Windows 10",
            mobile=False,
            touch=False,
            original=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/112.0.0.0 Safari/537.36"
            ),
            weight=0.38,
            accept_header=DESKTOP_ACCEPT_HEADER,
            accept_language_hint=desktop_locale.language,
        ),
        UserAgentRecord(
            id="desktop_firefox",
            family="Firefox",
            version="116.0",
            device="desktop",
            os="Windows 10",
            mobile=False,
            touch=False,
            original=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:116.0) Gecko/20100101 Firefox/116.0"
            ),
            weight=0.07,
            accept_header=DESKTOP_ACCEPT_HEADER,
            accept_language_hint=desktop_locale.language,
        ),
        UserAgentRecord(
            id="desktop_safari",
            family="Safari",
            version="16.5",
            device="desktop",
            os="macOS 13.4",
            mobile=False,
            touch=False,
            original=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 "
                "(KHTML, like Gecko) Version/16.5 Safari/605.1.15"
            ),
            weight=0.19,
            accept_header=DESKTOP_ACCEPT_HEADER,
            accept_language_hint="en-US,en;q=0.8",
        ),
        UserAgentRecord(
            id="mobile_android",
            family="Chrome",
            version="110.0.5481.153",
            device="mobile",
            os="Android 13",
            mobile=True,
            touch=True,
            original=(
                "Mozilla/5.0 (Linux; Android 13; Pixel 7 Pro) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/110.0.0.0 Mobile Safari/537.36"
            ),
            weight=0.24,
            accept_header=MOBILE_ACCEPT_HEADER,
            accept_language_hint=mobile_locale.language,
        ),
        UserAgentRecord(
            id="mobile_ios",
            family="Safari",
            version="16.3",
            device="mobile",
            os="iOS 16.3",
            mobile=True,
            touch=True,
            original=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_3 like Mac OS X) AppleWebKit/605.1.15 "
                "(KHTML, like Gecko) Version/16.3 Mobile/15E148 Safari/604.1"
            ),
            weight=0.12,
            accept_header=MOBILE_ACCEPT_HEADER,
            accept_language_hint="en-US,en;q=0.8",
        ),
    ]


class UserAgentProvider:
    """Provides weighted user-agent metadata with optional remote refresh."""

    def __init__(self, records: Sequence[UserAgentRecord] | None = None) -> None:
        self._records: list[UserAgentRecord] = []
        self._index: dict[str, UserAgentRecord] = {}
        self.extend(records or _builtin_user_agents())

    def all(self) -> list[UserAgentRecord]:
        return list(self._records)

    def random(self) -> UserAgentRecord:
        if not self._records:
            raise RuntimeError("UserAgentProvider has no records loaded")
        weights = [record.weight for record in self._records]
        return random.choices(self._records, weights=weights, k=1)[0]

    def get(self, profile_id: str) -> UserAgentRecord:
        try:
            return self._index[profile_id]
        except KeyError as exc:
            raise KeyError(f"Unknown user agent profile id: {profile_id}") from exc

    def extend(self, records: Iterable[UserAgentRecord]) -> None:
        for record in records:
            self._index[record.id] = record
        # maintain deterministic ordering: rebuild list sorted by weight descending
        self._records = sorted(self._index.values(), key=lambda item: item.weight, reverse=True)

    @classmethod
    def from_json_file(cls, path: str | Path) -> "UserAgentProvider":
        with Path(path).open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict) and "user_agents" in payload:
            payload = payload["user_agents"]
        records = []
        for item in payload:
            try:
                records.append(UserAgentRecord(**item))
            except ValidationError as exc:
                LOGGER.warning("Invalid user agent record skipped: %s", exc)
        return cls(records)

    @classmethod
    def from_remote(cls, url: str, timeout: float = 5.0) -> "UserAgentProvider":
        try:
            response = httpx.get(url, timeout=timeout)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Failed to fetch user agents from {url}: {exc}") from exc
        data = response.json()
        if isinstance(data, dict) and "user_agents" in data:
            data = data["user_agents"]
        records = []
        for item in data:
            try:
                records.append(UserAgentRecord(**item))
            except ValidationError as exc:
                LOGGER.debug("Skipping invalid user agent entry from %s: %s", url, exc)
        return cls(records or _builtin_user_agents())


__all__ = ["UserAgentProvider", "UserAgentRecord"]
