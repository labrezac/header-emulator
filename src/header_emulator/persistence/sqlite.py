"""SQLite persistence for sharing rotation state across processes."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Optional

from ..types import ProxyConfig
from .base import CooldownStore, PersistenceAdapter, ProxyStickyStore, StickyStore


_SCHEMA = """
CREATE TABLE IF NOT EXISTS sticky_sessions (
    token TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    expires_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sticky_proxies (
    token TEXT PRIMARY KEY,
    proxy_json TEXT NOT NULL,
    expires_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS cooldowns (
    profile_id TEXT PRIMARY KEY,
    expires_at REAL NOT NULL
);
"""


class SQLitePersistenceAdapter(PersistenceAdapter):
    def __init__(self, path: str | Path = ":memory:") -> None:
        self._lock = threading.RLock()
        self._path, self._conn_kwargs = self._normalize_path(path)
        with self._connection() as conn:
            conn.executescript(_SCHEMA)
        self._sticky_sessions = SQLiteStickyStore(self._connection, self._lock)
        self._sticky_proxies = SQLiteProxyStickyStore(self._connection, self._lock)
        self._cooldowns = SQLiteCooldownStore(self._connection, self._lock)

    def _normalize_path(self, path: str | Path) -> tuple[str, dict[str, object]]:
        path_str = str(path)
        kwargs: dict[str, object] = {"check_same_thread": False}
        if path_str == ":memory:":
            path_str = "file:header_emulator_mem?mode=memory&cache=shared"
            kwargs["uri"] = True
        return path_str, kwargs

    @contextmanager
    def _connection(self) -> Iterable[sqlite3.Connection]:
        with sqlite3.connect(self._path, **self._conn_kwargs) as conn:
            conn.row_factory = sqlite3.Row
            yield conn

    def sticky_sessions(self) -> StickyStore:
        return self._sticky_sessions

    def sticky_proxies(self) -> ProxyStickyStore:
        return self._sticky_proxies

    def cooldowns(self) -> CooldownStore:
        return self._cooldowns


class SQLiteStickyStore(StickyStore):
    def __init__(self, connection_factory, lock: threading.RLock) -> None:
        self._connection_factory = connection_factory
        self._lock = lock

    @contextmanager
    def _conn(self):
        with self._lock:
            with self._connection_factory() as conn:
                yield conn

    def get(self, token: str) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT profile_id, expires_at FROM sticky_sessions WHERE token = ?",
                (token,),
            ).fetchone()
        if row is None:
            return None
        if row["expires_at"] <= time.time():
            self.delete(token)
            return None
        return row["profile_id"]

    def set(self, token: str, profile_id: str, ttl_seconds: int) -> None:
        expires_at = time.time() + ttl_seconds
        with self._conn() as conn:
            conn.execute(
                "REPLACE INTO sticky_sessions (token, profile_id, expires_at) VALUES (?, ?, ?)",
                (token, profile_id, expires_at),
            )
            conn.commit()

    def delete(self, token: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM sticky_sessions WHERE token = ?", (token,))
            conn.commit()

    def prune(self) -> None:
        now = time.time()
        with self._conn() as conn:
            conn.execute("DELETE FROM sticky_sessions WHERE expires_at <= ?", (now,))
            conn.commit()


class SQLiteProxyStickyStore(ProxyStickyStore):
    def __init__(self, connection_factory, lock: threading.RLock) -> None:
        self._connection_factory = connection_factory
        self._lock = lock

    @contextmanager
    def _conn(self):
        with self._lock:
            with self._connection_factory() as conn:
                yield conn

    def get(self, token: str) -> Optional[ProxyConfig]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT proxy_json, expires_at FROM sticky_proxies WHERE token = ?",
                (token,),
            ).fetchone()
        if row is None:
            return None
        if row["expires_at"] <= time.time():
            self.delete(token)
            return None
        payload = json.loads(row["proxy_json"])
        return ProxyConfig.model_validate(payload)

    def set(self, token: str, proxy: ProxyConfig, ttl_seconds: int) -> None:
        expires_at = time.time() + ttl_seconds
        proxy_json = proxy.model_dump_json()
        with self._conn() as conn:
            conn.execute(
                "REPLACE INTO sticky_proxies (token, proxy_json, expires_at) VALUES (?, ?, ?)",
                (token, proxy_json, expires_at),
            )
            conn.commit()

    def delete(self, token: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM sticky_proxies WHERE token = ?", (token,))
            conn.commit()

    def prune(self) -> None:
        now = time.time()
        with self._conn() as conn:
            conn.execute("DELETE FROM sticky_proxies WHERE expires_at <= ?", (now,))
            conn.commit()


class SQLiteCooldownStore(CooldownStore):
    def __init__(self, connection_factory, lock: threading.RLock) -> None:
        self._connection_factory = connection_factory
        self._lock = lock

    @contextmanager
    def _conn(self):
        with self._lock:
            with self._connection_factory() as conn:
                yield conn

    def set(self, profile_id: str, expires_at: float) -> None:
        with self._conn() as conn:
            conn.execute(
                "REPLACE INTO cooldowns (profile_id, expires_at) VALUES (?, ?)",
                (profile_id, expires_at),
            )
            conn.commit()

    def get(self, profile_id: str) -> Optional[float]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT expires_at FROM cooldowns WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()
        if row is None:
            return None
        expires_at = row["expires_at"]
        if expires_at <= time.time():
            self.remove(profile_id)
            return None
        return expires_at

    def remove(self, profile_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM cooldowns WHERE profile_id = ?", (profile_id,))
            conn.commit()

    def prune(self, now: float) -> Iterable[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT profile_id FROM cooldowns WHERE expires_at <= ?",
                (now,),
            ).fetchall()
            conn.execute("DELETE FROM cooldowns WHERE expires_at <= ?", (now,))
            conn.commit()
        return [row["profile_id"] for row in rows]


__all__ = ["SQLitePersistenceAdapter"]
