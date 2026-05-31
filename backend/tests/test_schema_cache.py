"""Tests for TTL schema cache."""

from unittest.mock import patch

from app.schema_cache import (
    get_cached_schema_text,
    get_cache_status,
    invalidate_memory_cache,
    set_cached_snapshot,
)
from app.schema_snapshot import SchemaSnapshot, TableInfo


def _snapshot(text: str = "Table: t\nColumns: c") -> SchemaSnapshot:
    return SchemaSnapshot(
        tables=[TableInfo(name="t", columns=["c"])],
        relationships=[],
        text=text,
        content_hash="abc123",
        graph={"nodes": [], "edges": []},
    )


def test_cache_returns_snapshot_without_db_when_warm():
    invalidate_memory_cache()
    set_cached_snapshot(_snapshot("cached schema"))
    with patch("app.schema_cache.capture_schema_snapshot") as cap:
        assert get_cached_schema_text() == "cached schema"
        cap.assert_not_called()


def test_cache_refreshes_after_ttl(monkeypatch):
    invalidate_memory_cache()
    set_cached_snapshot(_snapshot("old"))
    monkeypatch.setattr("app.schema_cache._ttl_seconds", lambda: 0)

    fresh = _snapshot("new schema")
    with patch("app.schema_cache.capture_schema_snapshot", return_value=fresh):
        assert get_cached_schema_text() == "new schema"


def test_force_refresh_bypasses_ttl(monkeypatch):
    invalidate_memory_cache()
    set_cached_snapshot(_snapshot("stale"))
    monkeypatch.setattr("app.schema_cache._ttl_seconds", lambda: 99999)

    fresh = _snapshot("forced")
    with patch("app.schema_cache.capture_schema_snapshot", return_value=fresh) as cap:
        assert get_cached_schema_text(force_refresh=True) == "forced"
        cap.assert_called_once()


def test_cache_status_reports_stale_when_empty():
    invalidate_memory_cache()
    status = get_cache_status()
    assert status.is_stale is True
    assert status.table_count == 0
