"""
schema_sync.py — Background schema sync, TTL refresh, and semantic cache invalidation.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app import config
from app.schema_cache import (
    get_cached_snapshot,
    get_cache_status,
    record_sync_result,
    set_cached_snapshot,
)
from app.schema_index import index_schema_snapshot
from app.schema_snapshot import capture_schema_snapshot

from app.opensearch_client import get_opensearch_client

_stop_event = threading.Event()
_worker: threading.Thread | None = None

_STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "schema_sync_state.json"


@dataclass
class SyncResult:
    ok: bool
    content_hash: str
    schema_changed: bool
    schema_docs_indexed: int
    query_cache_cleared: int
    message: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "content_hash": self.content_hash,
            "schema_changed": self.schema_changed,
            "schema_docs_indexed": self.schema_docs_indexed,
            "query_cache_cleared": self.query_cache_cleared,
            "message": self.message,
            "error": self.error,
        }


def _load_persisted_hash() -> str:
    try:
        if _STATE_PATH.is_file():
            data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
            return str(data.get("content_hash") or "")
    except Exception:
        pass
    return ""


def _persist_hash(content_hash: str) -> None:
    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(
            json.dumps(
                {"content_hash": content_hash, "updated_at": time.time()},
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"[schema_sync] Could not persist state: {exc}")


def clear_semantic_query_cache() -> int:
    """Delete all documents in the question→SQL cache index after schema change."""
    client = get_opensearch_client()
    if client is None:
        return 0
    index_name = config.OPENSEARCH_INDEX_NAME
    if not client.indices.exists(index=index_name):
        return 0
    try:
        resp = client.delete_by_query(
            index=index_name,
            body={"query": {"match_all": {}}},
            refresh=True,
            conflicts="proceed",
        )
        deleted = resp.get("deleted", 0)
        return int(deleted) if deleted is not None else 0
    except Exception as exc:
        print(f"[schema_sync] clear_semantic_query_cache failed: {exc}")
        return 0


def run_schema_sync() -> SyncResult:
    """
    Capture live schema, refresh TTL cache, sync OpenSearch schema index,
    and clear semantic query cache when the schema hash changes.
    """
    if not getattr(config, "SCHEMA_SYNC_ENABLED", True):
        return SyncResult(
            ok=True,
            content_hash=get_cached_snapshot().content_hash,
            schema_changed=False,
            schema_docs_indexed=0,
            query_cache_cleared=0,
            message="schema sync disabled",
        )

    try:
        snapshot = capture_schema_snapshot()
    except Exception as exc:
        result = SyncResult(
            ok=False,
            content_hash="",
            schema_changed=False,
            schema_docs_indexed=0,
            query_cache_cleared=0,
            message="schema capture failed",
            error=str(exc),
        )
        record_sync_result(result.to_dict())
        return result

    set_cached_snapshot(snapshot)

    previous = _load_persisted_hash()
    schema_changed = (not previous) or (previous != snapshot.content_hash)

    docs_indexed = 0
    cache_cleared = 0
    index_err: str | None = None

    if (
        schema_changed
        and getattr(config, "SCHEMA_INDEX_ENABLED", True)
        and (config.OPENAI_API_KEY or "").strip()
    ):
        docs_indexed, index_err = index_schema_snapshot(snapshot)

    if schema_changed:
        cache_cleared = clear_semantic_query_cache()
        _persist_hash(snapshot.content_hash)

    msg_parts = ["schema synced"]
    if schema_changed:
        msg_parts.append("hash changed — query cache cleared")
    if docs_indexed:
        msg_parts.append(f"{docs_indexed} schema vectors indexed")
    if index_err:
        msg_parts.append(f"index warning: {index_err}")

    result = SyncResult(
        ok=index_err is None or docs_indexed > 0 or not getattr(config, "SCHEMA_INDEX_ENABLED", True),
        content_hash=snapshot.content_hash,
        schema_changed=schema_changed,
        schema_docs_indexed=docs_indexed,
        query_cache_cleared=cache_cleared,
        message="; ".join(msg_parts),
        error=index_err,
    )
    record_sync_result(result.to_dict())
    print(f"[schema_sync] {result.message} (hash={snapshot.content_hash[:12]}…)")
    return result


def _background_loop() -> None:
    interval = max(60, int(getattr(config, "SCHEMA_SYNC_INTERVAL_SECONDS", 300) or 300))
    while not _stop_event.is_set():
        try:
            run_schema_sync()
        except Exception as exc:
            print(f"[schema_sync] background error: {exc}")
        if _stop_event.wait(interval):
            break


def start_background_schema_sync() -> None:
    """Start daemon thread for periodic schema sync (idempotent)."""
    global _worker
    if not getattr(config, "SCHEMA_SYNC_ENABLED", True):
        return
    if _worker is not None and _worker.is_alive():
        return
    _stop_event.clear()

    def _bootstrap() -> None:
        try:
            run_schema_sync()
        except Exception as exc:
            print(f"[schema_sync] initial sync failed: {exc}")
        _background_loop()

    _worker = threading.Thread(target=_bootstrap, daemon=True, name="schema-sync")
    _worker.start()


def stop_background_schema_sync() -> None:
    _stop_event.set()
    global _worker
    if _worker is not None:
        _worker.join(timeout=5.0)
        _worker = None


def get_sync_status() -> dict[str, Any]:
    cache = get_cache_status()
    return {
        "cache": {
            "content_hash": cache.content_hash,
            "cached_at": cache.cached_at,
            "ttl_seconds": cache.ttl_seconds,
            "expires_at": cache.expires_at,
            "is_stale": cache.is_stale,
            "table_count": cache.table_count,
            "relationship_count": cache.relationship_count,
        },
        "last_sync": cache.last_sync,
        "persisted_hash": _load_persisted_hash(),
        "graph_node_count": len((get_cached_snapshot().graph or {}).get("nodes") or []),
        "graph_edge_count": len((get_cached_snapshot().graph or {}).get("edges") or []),
    }
