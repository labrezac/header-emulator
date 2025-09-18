"""Locale provider for Accept-Language rotation."""

from __future__ import annotations

import random
from typing import Iterable, Sequence

from ..constants import ACCEPT_LANGUAGE_WEIGHTS
from ..types import LocaleProfile


def _build_locales() -> list[LocaleProfile]:
    locales: list[LocaleProfile] = []
    for header, weight in ACCEPT_LANGUAGE_WEIGHTS.items():
        token = header.split(",")[0]
        country = None
        if "-" in token:
            _, country = token.split("-", 1)
        locales.append(
            LocaleProfile(
                language=header,
                quality=1.0,
                country=country,
            )
        )
    return locales


class LocaleProvider:
    """Weighted locale selector using Accept-Language headers."""

    def __init__(self, locales: Sequence[LocaleProfile] | None = None) -> None:
        self._locales = list(locales or _build_locales())

    def all(self) -> list[LocaleProfile]:
        return list(self._locales)

    def random(self) -> LocaleProfile:
        if not self._locales:
            raise RuntimeError("LocaleProvider has no locales configured")
        weights = [ACCEPT_LANGUAGE_WEIGHTS.get(locale.language, 1.0) for locale in self._locales]
        return random.choices(self._locales, weights=weights, k=1)[0]

    def extend(self, locales: Iterable[LocaleProfile]) -> None:
        for locale in locales:
            self._locales.append(locale)


__all__ = ["LocaleProvider"]
