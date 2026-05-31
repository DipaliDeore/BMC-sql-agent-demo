"""
schema_cache.py — TTL in-memory cache for schema text and snapshot metadata.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

from app import config
from app.schema_snapshot import SchemaSnapshot, capture_schema_snapshot

_lock = threading.Lock()
_cached: SchemaSnapshot | None = None
_cached_at: float = 0.0
_last_sync_at: float = 0.0
_last_sync_result: dict[str, Any] | None = None


@dataclass
class SchemaCacheStatus:
    content_hash: str
    cached_at: float
    ttl_seconds: int
    expires_at: float
    table_count: int
    relationship_count: int
    is_stale: bool
    last_sync: dict[str, Any] | None


def _ttl_seconds() -> int:
    return max(30, int(getattr(config, "SCHEMA_CACHE_TTL_SECONDS", 300) or 300))


def _is_expired() -> bool:
    if _cached is None:
        return True
    return (time.time() - _cached_at) >= _ttl_seconds()


def set_cached_snapshot(snapshot: SchemaSnapshot) -> None:
    global _cached, _cached_at
    with _lock:
        _cached = snapshot
        _cached_at = time.time()


def get_cached_snapshot(*, force_refresh: bool = False) -> SchemaSnapshot:
    """Return cached snapshot; refresh from DB when TTL expired or forced."""
    global _cached, _cached_at

    if not force_refresh and not _is_expired():
        with _lock:
            if _cached is not None:
                return _cached

    snapshot = capture_schema_snapshot()
    set_cached_snapshot(snapshot)
    return snapshot


def get_cached_schema_text(*, force_refresh: bool = False) -> str:
    return get_cached_snapshot(force_refresh=force_refresh).text


def get_cached_schema_hash() -> str:
    return get_cached_snapshot().content_hash


def get_cached_graph() -> dict[str, Any]:
    return dict(get_cached_snapshot().graph or {})


def record_sync_result(result: dict[str, Any]) -> None:
    global _last_sync_at, _last_sync_result
    with _lock:
        _last_sync_at = time.time()
        _last_sync_result = dict(result)


def get_cache_status() -> SchemaCacheStatus:
    with _lock:
        snap = _cached
        cached_at = _cached_at
        sync_meta = dict(_last_sync_result) if _last_sync_result else None

    ttl = _ttl_seconds()
    now = time.time()
    if snap is None:
        return SchemaCacheStatus(
            content_hash="",
            cached_at=0.0,
            ttl_seconds=ttl,
            expires_at=0.0,
            table_count=0,
            relationship_count=0,
            is_stale=True,
            last_sync=sync_meta,
        )

    return SchemaCacheStatus(
        content_hash=snap.content_hash,
        cached_at=cached_at,
        ttl_seconds=ttl,
        expires_at=cached_at + ttl,
        table_count=len(snap.tables),
        relationship_count=len(snap.relationships),
        is_stale=_is_expired(),
        last_sync=sync_meta,
    )


def invalidate_memory_cache() -> None:
    global _cached, _cached_at
    with _lock:
        _cached = None
        _cached_at = 0.0
