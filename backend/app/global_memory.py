"""
global_memory.py — Single-user cross-chat long-term memory (one evolving summary).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app import config
from app import chat_store
from app.checkpointer import get_postgres_pool
from app.conversation_context import build_context_from_messages
from app.memory.summary import generate_global_memory_summary

# pyrefly: ignore [missing-import]
from psycopg.rows import dict_row

_MEM_ROW: dict[str, Any] = {"memory_summary": "", "updated_at": None}
# chat_id -> chat updated_at ISO string at last successful merge (in-memory fallback)
_MEM_MERGED: dict[str, str] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _chat_updated_at(chat_id: str) -> str:
    row = chat_store.get_chat(chat_id)
    if not row:
        return ""
    return str(row.get("updated_at") or "")


def _get_merged_snapshot(chat_id: str) -> str | None:
    """Return chat ``updated_at`` ISO recorded at last merge, or None if never merged."""
    pool = get_postgres_pool()
    if pool is None:
        return _MEM_MERGED.get(chat_id)

    try:
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT chat_updated_at FROM global_memory_merged_chats
                    WHERE chat_id = %s
                    """,
                    (chat_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        ts = row.get("chat_updated_at")
        if hasattr(ts, "isoformat"):
            return ts.isoformat()
        return str(ts) if ts is not None else None
    except Exception as exc:
        print(f"[global_memory] _get_merged_snapshot failed: {exc}")
        return None


def _mark_chat_merged(chat_id: str, chat_updated_at: str) -> None:
    snap = (chat_updated_at or "").strip()
    pool = get_postgres_pool()
    if pool is None:
        if snap:
            _MEM_MERGED[chat_id] = snap
        return

    try:
        ts = _parse_ts(snap) or datetime.now(timezone.utc)
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO global_memory_merged_chats (chat_id, chat_updated_at, merged_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (chat_id) DO UPDATE SET
                        chat_updated_at = EXCLUDED.chat_updated_at,
                        merged_at = EXCLUDED.merged_at
                    """,
                    (chat_id, ts),
                )
    except Exception as exc:
        print(f"[global_memory] _mark_chat_merged failed: {exc}")


def chat_needs_global_merge(chat_id: str) -> bool:
    """True when chat has messages and is new or changed since last merge."""
    cid = (chat_id or "").strip()
    if not cid or chat_store.get_chat(cid) is None:
        return False
    if not chat_store.list_messages(cid):
        return False
    current = _chat_updated_at(cid)
    if not current:
        return True
    prior = _get_merged_snapshot(cid)
    if prior is None:
        return True
    cur_dt = _parse_ts(current)
    pri_dt = _parse_ts(prior)
    if cur_dt and pri_dt:
        return cur_dt > pri_dt
    return current != prior


def get_global_memory() -> str:
    """Return the current long-term memory summary (empty if none)."""
    if not getattr(config, "GLOBAL_MEMORY_ENABLED", True):
        return ""

    pool = get_postgres_pool()
    if pool is None:
        return (_MEM_ROW.get("memory_summary") or "").strip()

    try:
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT memory_summary FROM global_memory
                    ORDER BY id ASC
                    LIMIT 1
                    """
                )
                row = cur.fetchone()
        if not row:
            return ""
        return (row.get("memory_summary") or "").strip()
    except Exception as exc:
        print(f"[global_memory] get_global_memory failed: {exc}")
        return ""


def update_global_memory(memory_summary: str) -> None:
    """Overwrite the single global memory row."""
    text = (memory_summary or "").strip()
    cap = int(getattr(config, "GLOBAL_SUMMARY_MAX_CHARS", 8000) or 8000)
    if len(text) > cap:
        text = text[:cap] + "…"

    pool = get_postgres_pool()
    if pool is None:
        _MEM_ROW["memory_summary"] = text
        _MEM_ROW["updated_at"] = _now_iso()
        return

    try:
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT id FROM global_memory ORDER BY id ASC LIMIT 1"
                )
                row = cur.fetchone()
                if row:
                    cur.execute(
                        """
                        UPDATE global_memory
                        SET memory_summary = %s, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (text, row["id"]),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO global_memory (memory_summary, updated_at)
                        VALUES (%s, NOW())
                        """,
                        (text,),
                    )
    except Exception as exc:
        print(f"[global_memory] update_global_memory failed: {exc}")


def inject_global_memory() -> str:
    """System-prompt block for cross-chat memory (empty when disabled or unset)."""
    if not getattr(config, "GLOBAL_MEMORY_ENABLED", True):
        return ""
    summary = get_global_memory().strip()
    if not summary:
        return ""
    return (
        "--- GLOBAL LONG-TERM MEMORY (prior chats; single user) ---\n"
        f"{summary}\n"
        "--- END GLOBAL MEMORY ---\n"
        "Use this for stable preferences and recurring topics. "
        "For this thread only, still follow PRIOR CONVERSATION below when present."
    )


def _format_chat_transcript(chat_id: str) -> str:
    messages = chat_store.list_messages(chat_id)
    if not messages:
        return ""
    return build_context_from_messages(messages, exclude_trailing_user=False)


def merge_chat_into_global_memory(chat_id: str, *, force: bool = False) -> dict[str, Any]:
    """
    Merge one chat into the global summary.

    Skips when already merged at the same chat ``updated_at`` unless ``force=True``.
    """
    if not getattr(config, "GLOBAL_MEMORY_ENABLED", True):
        return {"ok": True, "updated": False, "message": "global memory disabled"}

    cid = (chat_id or "").strip()
    if not cid:
        return {"ok": True, "updated": False, "message": "no chat_id"}

    if chat_store.get_chat(cid) is None:
        return {"ok": False, "updated": False, "message": "chat not found"}

    transcript = _format_chat_transcript(cid)
    if not transcript.strip():
        return {"ok": True, "updated": False, "message": "chat has no messages"}

    if not force and not chat_needs_global_merge(cid):
        return {"ok": True, "updated": False, "message": "already merged"}

    prior = get_global_memory()
    new_summary = generate_global_memory_summary(prior, transcript)
    if not (new_summary or "").strip():
        return {"ok": True, "updated": False, "message": "summary unchanged"}

    update_global_memory(new_summary)
    snap = _chat_updated_at(cid)
    _mark_chat_merged(cid, snap)
    return {
        "ok": True,
        "updated": True,
        "memory_chars": len(new_summary),
        "message": "global memory updated",
    }


def merge_pending_chats(*, exclude_chat_id: str | None = None) -> dict[str, Any]:
    """
    Merge all chats that have new messages since their last merge.

    ``exclude_chat_id``: skip the active thread (e.g. user is still typing in it).
    Processes oldest chats first so summaries fold chronologically.
    """
    if not getattr(config, "GLOBAL_MEMORY_ENABLED", True):
        return {"ok": True, "merged_chats": 0, "message": "global memory disabled"}

    exclude = (exclude_chat_id or "").strip()
    chats = list(reversed(chat_store.list_chats(limit=200)))
    merged = 0
    errors: list[str] = []

    for chat in chats:
        cid = (chat.get("id") or "").strip()
        if not cid or (exclude and cid == exclude):
            continue
        if not chat_needs_global_merge(cid):
            continue
        result = merge_chat_into_global_memory(cid)
        if result.get("updated"):
            merged += 1
        elif not result.get("ok"):
            errors.append(f"{cid}: {result.get('message', 'failed')}")

    out: dict[str, Any] = {
        "ok": not errors,
        "merged_chats": merged,
        "message": f"merged {merged} chat(s)" if merged else "no pending chats",
    }
    if errors:
        out["errors"] = errors
    return out
