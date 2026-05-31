"""Tests for schema sync and semantic cache invalidation on hash change."""

from unittest.mock import MagicMock, patch

from app.schema_cache import invalidate_memory_cache
from app.schema_snapshot import SchemaSnapshot, TableInfo
from app.schema_sync import clear_semantic_query_cache, run_schema_sync


def _snap(hash_suffix: str) -> SchemaSnapshot:
    return SchemaSnapshot(
        tables=[TableInfo(name="t", columns=["c"])],
        relationships=[],
        text="schema",
        content_hash=f"hash_{hash_suffix}",
        graph={"nodes": [{"id": "t"}], "edges": []},
    )


def test_clear_semantic_query_cache_no_op_without_client():
    with patch("app.schema_sync.get_opensearch_client", return_value=None):
        assert clear_semantic_query_cache() == 0


def test_run_schema_sync_clears_query_cache_only_when_hash_changes(tmp_path, monkeypatch):
    invalidate_memory_cache()
    state_file = tmp_path / "schema_sync_state.json"
    monkeypatch.setattr("app.schema_sync._STATE_PATH", state_file)

    snap_a = _snap("a")

    with (
        patch("app.schema_sync.capture_schema_snapshot", return_value=snap_a),
        patch("app.schema_sync.index_schema_snapshot", return_value=(2, None)),
        patch("app.schema_sync.clear_semantic_query_cache", return_value=5) as clear_mock,
        patch("app.schema_sync.config.SCHEMA_SYNC_ENABLED", True),
        patch("app.schema_sync.config.SCHEMA_INDEX_ENABLED", True),
        patch("app.schema_sync.config.OPENAI_API_KEY", "sk-test"),
    ):
        r1 = run_schema_sync()
        assert r1.schema_changed is True
        assert r1.query_cache_cleared == 5
        clear_mock.assert_called_once()

        clear_mock.reset_mock()
        r2 = run_schema_sync()
        assert r2.schema_changed is False
        clear_mock.assert_not_called()


def test_run_schema_sync_skips_index_when_disabled(monkeypatch):
    invalidate_memory_cache()
    snap = _snap("only")
    with (
        patch("app.schema_sync._load_persisted_hash", return_value=""),
        patch("app.schema_sync.capture_schema_snapshot", return_value=snap),
        patch("app.schema_sync.index_schema_snapshot") as index_mock,
        patch("app.schema_sync.clear_semantic_query_cache", return_value=0),
        patch("app.schema_sync.config.SCHEMA_SYNC_ENABLED", True),
        patch("app.schema_sync.config.SCHEMA_INDEX_ENABLED", False),
    ):
        run_schema_sync()
        index_mock.assert_not_called()


def test_clear_semantic_query_cache_deletes_documents():
    client = MagicMock()
    client.indices.exists.return_value = True
    client.delete_by_query.return_value = {"deleted": 3}
    with patch("app.schema_sync.get_opensearch_client", return_value=client):
        assert clear_semantic_query_cache() == 3
        client.delete_by_query.assert_called_once()
