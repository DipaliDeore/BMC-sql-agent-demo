"""
Persistent rolling summary + structured memory per LangGraph thread_id (conversation_id).
Uses Postgres when POSTGRES_URI is set; otherwise in-process dict (dev / no-Postgres).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.checkpointer import get_postgres_pool

_MEM: dict[str, dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_thread_memory_row(thread_id: str) -> dict[str, Any]:
    """Return conversation_summary, structured_memory, last_summarized_at_message_count."""
    if not thread_id:
        return {
            "conversation_summary": "",
            "structured_memory": {},
            "last_summarized_at_message_count": 0,
        }
    pool = get_postgres_pool()
    if pool is None:
        row = _MEM.get(thread_id)
        if not row:
            return {
                "conversation_summary": "",
                "structured_memory": {},
                "last_summarized_at_message_count": 0,
            }
        return {
            "conversation_summary": row.get("conversation_summary") or "",
            "structured_memory": dict(row.get("structured_memory") or {}),
            "last_summarized_at_message_count": int(
                row.get("last_summarized_at_message_count") or 0
            ),
        }
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT conversation_summary, structured_memory,
                       last_summarized_at_message_count
                FROM bmcs_thread_memory WHERE thread_id = %s
                """,
                (thread_id,),
            )
            r = cur.fetchone()
            if not r:
                return {
                    "conversation_summary": "",
                    "structured_memory": {},
                    "last_summarized_at_message_count": 0,
                }
            sm = r.get("structured_memory")
            if isinstance(sm, str):
                try:
                    sm = json.loads(sm)
                except json.JSONDecodeError:
                    sm = {}
            return {
                "conversation_summary": r.get("conversation_summary") or "",
                "structured_memory": dict(sm or {}),
                "last_summarized_at_message_count": int(
                    r.get("last_summarized_at_message_count") or 0
                ),
            }


def upsert_thread_memory(
    thread_id: str,
    *,
    conversation_summary: str | None = None,
    structured_memory: dict[str, Any] | None = None,
    last_summarized_at_message_count: int | None = None,
) -> None:
    if not thread_id:
        return
    pool = get_postgres_pool()
    if pool is None:
        cur = _MEM.get(thread_id, {})
        if conversation_summary is not None:
            cur["conversation_summary"] = conversation_summary
        if structured_memory is not None:
            cur["structured_memory"] = dict(structured_memory)
        if last_summarized_at_message_count is not None:
            cur["last_summarized_at_message_count"] = int(last_summarized_at_message_count)
        cur["updated_at"] = _now_iso()
        _MEM[thread_id] = cur
        return
    row = get_thread_memory_row(thread_id)
    new_summary = (
        conversation_summary
        if conversation_summary is not None
        else row["conversation_summary"]
    )
    new_struct = (
        dict(structured_memory)
        if structured_memory is not None
        else row["structured_memory"]
    )
    new_last = (
        int(last_summarized_at_message_count)
        if last_summarized_at_message_count is not None
        else row["last_summarized_at_message_count"]
    )
    with pool.connection() as conn:
        with conn.cursor() as cur:
                cur.execute(
                """
                INSERT INTO bmcs_thread_memory (
                    thread_id, conversation_summary, structured_memory,
                    last_summarized_at_message_count, updated_at
                ) VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (thread_id) DO UPDATE SET
                    conversation_summary = EXCLUDED.conversation_summary,
                    structured_memory = EXCLUDED.structured_memory,
                    last_summarized_at_message_count =
                        EXCLUDED.last_summarized_at_message_count,
                    updated_at = NOW()
                """,
                (thread_id, new_summary, Json(new_struct), new_last),
            )
