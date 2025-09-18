"""Utilities for loading profile data from JSON or YAML files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

try:
    import yaml
except ImportError:  # pragma: no cover - optional dependency
    yaml = None

from .providers.locales import LocaleProvider
from .providers.user_agents import UserAgentProvider, UserAgentRecord
from .types import LocaleProfile


def load_profiles(path: str | Path) -> Tuple[UserAgentProvider, LocaleProvider]:
    """Load user-agent and locale profiles from a JSON or YAML file."""

    data = _read_file(path)
    ua_records = [UserAgentRecord(**item) for item in data.get("user_agents", [])]
    if not ua_records:
        raise RuntimeError("profile file contains no user-agent records")
    locale_entries = [LocaleProfile(**item) for item in data.get("locales", [])]
    if not locale_entries:
        locale_entries = [LocaleProfile(language="en-US,en;q=0.9", country="US")]
    return UserAgentProvider(ua_records), LocaleProvider(locale_entries)


def _read_file(path: str | Path) -> dict:
    payload = Path(path).read_text(encoding="utf-8")
    suffix = Path(path).suffix.lower()
    if suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML is required for YAML profile files")
        return yaml.safe_load(payload) or {}
    return json.loads(payload)


__all__ = ["load_profiles"]
