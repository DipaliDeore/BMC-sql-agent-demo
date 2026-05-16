"""
Chat sessions and messages for the UI. Uses Postgres when POSTGRES_URI is set;
otherwise an in-process dict (lost on restart).
"""

from __future__ import annotations

import json
import re
import uuid
from decimal import Decimal
from datetime import datetime, timezone, date
from typing import Any

# pyrefly: ignore [missing-import]
from psycopg.rows import dict_row
# pyrefly: ignore [missing-import]
from psycopg.types.json import Json

from app.checkpointer import get_postgres_pool
from app.serialization import make_json_serializable

_MEM_CHATS: dict[str, dict[str, Any]] = {}
_MEM_MESSAGES: dict[str, list[dict[str, Any]]] = {}


def _json_safe_payload(value: Any) -> Any:
    # Handle datetime and date objects
    if isinstance(value, (date, datetime)):
        return make_json_serializable(value)
    
    if isinstance(value, Decimal):
        return str(value)
    
    if isinstance(value, dict):
        return {k: _json_safe_payload(v) for k, v in value.items()}
    
    if isinstance(value, list):
        return [_json_safe_payload(v) for v in value]
    
    return value


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _title_from_question(q: str, max_len: int = 48) -> str:
    t = re.sub(r"\s+", " ", (q or "").strip())
    if not t:
        return "New chat"
    return (t[: max_len - 1] + "…") if len(t) > max_len else t


def init_chat_schema() -> None:
    pool = get_postgres_pool()
    if pool is None:
        return
    statements = [
        """
        CREATE TABLE IF NOT EXISTS bmcs_chats (
            id UUID PRIMARY KEY,
            title TEXT NOT NULL DEFAULT 'New chat',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS bmcs_chat_messages (
            id BIGSERIAL PRIMARY KEY,
            chat_id UUID NOT NULL REFERENCES bmcs_chats(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            payload JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_bmcs_chat_messages_chat_id
            ON bmcs_chat_messages (chat_id, id)
        """,
        """
        CREATE TABLE IF NOT EXISTS bmcs_thread_memory (
            thread_id TEXT PRIMARY KEY,
            conversation_summary TEXT NOT NULL DEFAULT '',
            structured_memory JSONB NOT NULL DEFAULT '{}'::jsonb,
            last_summarized_at_message_count INT NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
    ]
    with pool.connection() as conn:
        with conn.cursor() as cur:
            for sql in statements:
                cur.execute(sql)


def create_chat(title: str | None = None) -> dict[str, Any]:
    cid = str(uuid.uuid4())
    t = (title or "New chat").strip() or "New chat"
    pool = get_postgres_pool()
    if pool is None:
        _MEM_CHATS[cid] = {"id": cid, "title": t, "updated_at": _now_iso()}
        _MEM_MESSAGES[cid] = []
        return {"id": cid, "title": t, "updated_at": _MEM_CHATS[cid]["updated_at"]}
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO bmcs_chats (id, title) VALUES (%s, %s)",
                (cid, t),
            )
    return {"id": cid, "title": t, "updated_at": _now_iso()}


def list_chats(limit: int = 80) -> list[dict[str, Any]]:
    pool = get_postgres_pool()
    if pool is None:
        rows = sorted(
            _MEM_CHATS.values(),
            key=lambda r: r.get("updated_at") or "",
            reverse=True,
        )[:limit]
        return [{"id": r["id"], "title": r["title"], "updated_at": r["updated_at"]} for r in rows]
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id::text AS id, title, updated_at FROM bmcs_chats "
                "ORDER BY updated_at DESC LIMIT %s",
                (limit,),
            )
            out = []
            for row in cur.fetchall():
                ts = row["updated_at"]
                out.append(
                    {
                        "id": row["id"],
                        "title": row["title"],
                        "updated_at": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                    }
                )
            return out


def get_chat(chat_id: str) -> dict[str, Any] | None:
    pool = get_postgres_pool()
    if pool is None:
        return _MEM_CHATS.get(chat_id)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id::text AS id, title, updated_at FROM bmcs_chats WHERE id = %s",
                (chat_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            ts = row["updated_at"]
            return {
                "id": row["id"],
                "title": row["title"],
                "updated_at": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            }


def rename_chat(chat_id: str, title: str) -> bool:
    t = title.strip()
    if not t:
        return False
    pool = get_postgres_pool()
    if pool is None:
        if chat_id not in _MEM_CHATS:
            return False
        _MEM_CHATS[chat_id]["title"] = t
        _MEM_CHATS[chat_id]["updated_at"] = _now_iso()
        return True
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE bmcs_chats SET title = %s, updated_at = NOW() WHERE id = %s",
                (t, chat_id),
            )
            return cur.rowcount > 0


def delete_chat(chat_id: str) -> bool:
    pool = get_postgres_pool()
    if pool is None:
        _MEM_CHATS.pop(chat_id, None)
        _MEM_MESSAGES.pop(chat_id, None)
        return True
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM bmcs_chats WHERE id = %s", (chat_id,))
            return cur.rowcount > 0


def ensure_chat(chat_id: str) -> None:
    pool = get_postgres_pool()
    if pool is None:
        if chat_id not in _MEM_CHATS:
            _MEM_CHATS[chat_id] = {
                "id": chat_id,
                "title": "New chat",
                "updated_at": _now_iso(),
            }
            _MEM_MESSAGES[chat_id] = []
        return
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO bmcs_chats (id, title) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
                (chat_id, "New chat"),
            )


def touch_chat(chat_id: str) -> None:
    pool = get_postgres_pool()
    if pool is None:
        if chat_id in _MEM_CHATS:
            _MEM_CHATS[chat_id]["updated_at"] = _now_iso()
        return
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE bmcs_chats SET updated_at = NOW() WHERE id = %s", (chat_id,))


def maybe_set_title_from_first_question(chat_id: str, question: str) -> None:
    pool = get_postgres_pool()
    title = _title_from_question(question)
    if pool is None:
        c = _MEM_CHATS.get(chat_id)
        if not c:
            return
        if c.get("title") in ("New chat", "", None):
            c["title"] = title
            c["updated_at"] = _now_iso()
        return
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE bmcs_chats SET title = %s, updated_at = NOW() "
                "WHERE id = %s AND (title IS NULL OR title = '' OR title = 'New chat')",
                (title, chat_id),
            )


def add_message(
    chat_id: str,
    role: str,
    content: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_chat(chat_id)
    pool = get_postgres_pool()
    if pool is None:
        mid = len(_MEM_MESSAGES.get(chat_id, [])) + 1
        row = {
            "id": mid,
            "chat_id": chat_id,
            "role": role,
            "content": content,
            "payload": payload,
            "created_at": _now_iso(),
        }
        _MEM_MESSAGES.setdefault(chat_id, []).append(row)
        _MEM_CHATS[chat_id]["updated_at"] = _now_iso()
        return row
    with pool.connection() as conn:
        with conn.cursor() as cur:
            payload_for_db = _json_safe_payload(payload)
            cur.execute(
                "INSERT INTO bmcs_chat_messages (chat_id, role, content, payload) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (chat_id, role, content, Json(payload_for_db) if payload_for_db is not None else None),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("INSERT INTO bmcs_chat_messages did not return id")
            # Pool uses row_factory=dict_row — fetchone() is keyed by column name, not [0].
            try:
                mid = row["id"]
            except (KeyError, TypeError):
                mid = row[0]
            cur.execute(
                "UPDATE bmcs_chats SET updated_at = NOW() WHERE id = %s", (chat_id,)
            )
    return {
        "id": mid,
        "chat_id": chat_id,
        "role": role,
        "content": content,
        "payload": payload_for_db if pool is not None else payload,
        "created_at": _now_iso(),
    }


def get_message(chat_id: str, message_id: int) -> dict[str, Any] | None:
    """Return one message row (id, role, content, payload, …) or None."""
    pool = get_postgres_pool()
    if pool is None:
        for m in _MEM_MESSAGES.get(chat_id, []):
            try:
                if int(m["id"]) == int(message_id):
                    return m
            except (TypeError, ValueError):
                continue
        return None
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, chat_id::text AS chat_id, role, content, payload, created_at "
                "FROM bmcs_chat_messages WHERE chat_id = %s AND id = %s",
                (chat_id, message_id),
            )
            row = cur.fetchone()
            if not row:
                return None
            pl = row["payload"]
            if isinstance(pl, str):
                try:
                    pl = json.loads(pl)
                except json.JSONDecodeError:
                    pl = None
            return {
                "id": row["id"],
                "chat_id": row["chat_id"],
                "role": row["role"],
                "content": row["content"],
                "payload": pl,
                "created_at": row["created_at"],
            }


def list_messages(chat_id: str) -> list[dict[str, Any]]:
    pool = get_postgres_pool()
    if pool is None:
        return list(_MEM_MESSAGES.get(chat_id, []))
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, role, content, payload, created_at "
                "FROM bmcs_chat_messages WHERE chat_id = %s ORDER BY id ASC",
                (chat_id,),
            )
            rows = cur.fetchall()
            out = []
            for row in rows:
                ts = row["created_at"]
                pl = row["payload"]
                if isinstance(pl, str):
                    try:
                        pl = json.loads(pl)
                    except json.JSONDecodeError:
                        pl = None
                out.append(
                    {
                        "id": row["id"],
                        "role": row["role"],
                        "content": row["content"],
                        "payload": pl,
                        "created_at": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                    }
                )
            return out


def transcript_for_prompt(chat_id: str, max_turns: int = 40) -> str:
    """Compact transcript for augmenting the current question (backup context)."""
    msgs = list_messages(chat_id)
    if not msgs:
        return ""
    lines: list[str] = []
    for m in msgs[-max_turns:]:
        r = m.get("role") or ""
        c = (m.get("content") or "").strip()
        if not c:
            continue
        label = "User" if r == "user" else "Assistant"
        lines.append(f"{label}: {c}")
    return "\n".join(lines)
