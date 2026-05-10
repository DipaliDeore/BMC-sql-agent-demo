"""
Shared LangGraph checkpointer: Postgres (pool) when POSTGRES_URI is set, else in-memory.
Must be initialized before compiling graphs — see app.main lifespan.
"""

from __future__ import annotations

import threading

# pyrefly: ignore [missing-import]
from langgraph.checkpoint.memory import InMemorySaver
# pyrefly: ignore [missing-import]
from langgraph.checkpoint.postgres import PostgresSaver
# pyrefly: ignore [missing-import]
from psycopg import errors as pg_errors
# pyrefly: ignore [missing-import]
from psycopg.rows import dict_row
# pyrefly: ignore [missing-import]
from psycopg_pool import ConnectionPool

from app import config

_PG_PUBLIC_SCHEMA_HELP = """
PostgreSQL refused CREATE on schema 'public' for your database user (common on PostgreSQL 15+).

Fix (run once as superuser, e.g. user 'postgres'), connected to YOUR app database:

  GRANT USAGE, CREATE ON SCHEMA public TO your_app_user;

Replace your_app_user with the username from POSTGRES_URI (before the password).

Or use the postgres superuser in POSTGRES_URI for local dev.

See backend/scripts/postgres_app_grants.sql in this repo.
""".strip()

_pool: ConnectionPool | None = None
_pg_saver: PostgresSaver | None = None
_memory_saver: InMemorySaver | None = None
_lock = threading.Lock()
_initialized = False


def init_checkpointer() -> None:
    """Create Postgres pool + saver (with migrations) or fall back to in-memory."""
    global _pool, _pg_saver, _memory_saver, _initialized
    with _lock:
        if _initialized:
            return
        uri = (config.POSTGRES_URI or "").strip()
        if uri:
            try:
                _pool = ConnectionPool(
                    conninfo=uri,
                    min_size=1,
                    max_size=10,
                    kwargs={
                        "autocommit": True,
                        "prepare_threshold": 0,
                        "row_factory": dict_row,
                    },
                )
                _pg_saver = PostgresSaver(_pool)
                _pg_saver.setup()
            except Exception as e:
                if _pool is not None:
                    try:
                        _pool.close()
                    except Exception:
                        pass
                    _pool = None
                _pg_saver = None
                if isinstance(e, pg_errors.InsufficientPrivilege) or (
                    "permission denied for schema public" in str(e).lower()
                ):
                    raise RuntimeError(_PG_PUBLIC_SCHEMA_HELP) from e
                raise
        else:
            _memory_saver = InMemorySaver()
        _initialized = True


def get_checkpointer():
    """Return the active checkpointer (Postgres-backed when configured)."""
    init_checkpointer()
    if _pg_saver is not None:
        return _pg_saver
    assert _memory_saver is not None
    return _memory_saver


def get_postgres_pool() -> ConnectionPool | None:
    init_checkpointer()
    return _pool


def shutdown_checkpointer() -> None:
    global _pool, _pg_saver, _memory_saver, _initialized
    with _lock:
        if _pool is not None:
            _pool.close()
            _pool = None
        _pg_saver = None
        _memory_saver = None
        _initialized = False
