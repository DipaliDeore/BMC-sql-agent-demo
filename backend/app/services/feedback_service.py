from __future__ import annotations

"""
feedback_service.py — Thumbs feedback: semantic cache (vector DB) or file logging.

Routing (strict):
  * Only feedback == "up" (case-insensitive, after strip) → OpenSearch via store_query.
  * feedback == "down" → delete from OpenSearch if exists, log to file.
  * feedback == "none" or anything else → log to file only.
"""

import asyncio
import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app import config
from app.opensearch_client import get_opensearch_client
from app.store import make_stable_cache_doc_id, store_query


# ── Module-level lock — ONE lock shared by ALL threads ──────────────────────
# CORRECT approach: defined once at module level
# All threads share this SAME lock object
# When Thread 1 is writing, Thread 2 waits — no file corruption
# WRONG approach (old code): threading.Lock() inside function
# = each thread gets its OWN lock = no actual protection
_FEEDBACK_LOG_LOCK = threading.Lock()


# ── Log file path ────────────────────────────────────────────────────────────

def _get_log_file_path() -> Path:
    """
    Return path to feedback_logs.jsonl inside backend/logs/
    Creates the logs directory if it does not exist.
    """
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "feedback_logs.jsonl"


# ── Thread-safe file logging ─────────────────────────────────────────────────

def log_feedback_to_file(entry: dict) -> None:
    """
    Append one feedback entry to feedback_logs.jsonl.

    JSONL format: one JSON object per line.

    Thread-safe: uses module-level _FEEDBACK_LOG_LOCK.
    If 1000 users submit feedback at the same time:
      - Thread 1 acquires lock → writes → releases lock
      - Thread 2 waits → acquires lock → writes → releases lock
      - Never two threads writing simultaneously → no file corruption
    """
    log_file = _get_log_file_path()
    line = json.dumps(entry, ensure_ascii=False) + "\n"

    with _FEEDBACK_LOG_LOCK:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)


# ── Helper functions ─────────────────────────────────────────────────────────

def _is_thumbs_up(raw: Any) -> bool:
    """True only for explicit thumbs-up. Everything else is log-only."""
    if raw is None:
        return False
    return str(raw).strip().lower() == "up"


def _coerce_optional_str(value: Any) -> str:
    """Safely convert any value to stripped string."""
    if value is None:
        return ""
    return str(value).strip()


def _extract_sql_from_response(text: str) -> str:
    """
    Pull executed SQL from a combined assistant reply.
    Looks for SELECT or WITH statement in the response text.
    """
    if not text or not str(text).strip():
        return ""
    s = str(text).strip()
    blocks = re.split(r"\n\s*\n+", s)
    for block in reversed(blocks):
        t = block.strip()
        if re.match(r"(?is)^(with|select)\s+", t):
            return t
    m = re.search(r"(?is)\b(with|select)\s+[\s\S]+$", s)
    if m:
        return m.group(0).strip()
    return ""


def _sql_for_vector_index(body: "FeedbackRequest", response: str) -> str:
    """
    Get SQL to store in OpenSearch.
    Prefers explicit sql field from request.
    Falls back to parsing SQL from response text.
    """
    explicit = _coerce_optional_str(body.sql)
    if explicit:
        return explicit
    return _extract_sql_from_response(response)


# ── Pydantic models ──────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    """POST /feedback request body."""

    model_config = ConfigDict(extra="ignore")

    query: str = Field(default="", max_length=50_000)
    response: str = Field(default="", max_length=200_000)
    sql: str = Field(default="", max_length=50_000)
    feedback: Any = None
    metadata: Any = None
    session_id: str | None = None


class FeedbackResponse(BaseModel):
    """POST /feedback response body."""

    status: Literal["stored_in_vector_db", "logged"]


class FeedbackProcessingError(Exception):
    """Raised from worker thread. Converted to HTTPException in the route."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


# ── Core feedback logic ──────────────────────────────────────────────────────

def submit_feedback(body: FeedbackRequest) -> FeedbackResponse:
    """
    Route feedback to correct destination:

    thumbs up   → OpenSearch (with duplicate check)
    thumbs down → delete from OpenSearch if previously stored, log to file
    none/other  → log to file only
    """
    query       = (body.query or "").strip()
    response    = (body.response or "").strip()
    sql_val     = _coerce_optional_str(body.sql)
    session_id  = body.session_id or "unknown"
    feedback_type = str(body.feedback).strip().lower() if body.feedback else "none"

    # ── THUMBS UP ────────────────────────────────────────────────────────────
    if _is_thumbs_up(body.feedback):

        if not query:
            raise FeedbackProcessingError(
                422, "Thumbs-up requires a non-empty query."
            )

        sql_stored = _sql_for_vector_index(body, response)
        if not sql_stored:
            raise FeedbackProcessingError(
                422,
                "Thumbs-up requires SQL. Send the sql field from the assistant turn."
            )

        client = get_opensearch_client()
        if client is None:
            raise FeedbackProcessingError(
                503, "Vector store is not available. Check OPENSEARCH_URL."
            )

        index_name = config.OPENSEARCH_INDEX_NAME
        doc_id = make_stable_cache_doc_id(query, sql_stored)

        # Duplicate check — already in OpenSearch? Return early, no duplicate stored
        if client.exists(index=index_name, id=doc_id):
            return FeedbackResponse(status="stored_in_vector_db")

        # Append metadata to SQL if provided
        sql_for_store = sql_stored
        if isinstance(body.metadata, dict) and body.metadata:
            try:
                meta_json = json.dumps(
                    body.metadata, ensure_ascii=False, sort_keys=True
                )
                sql_for_store = (
                    f"{sql_stored}\n\n--- feedback_metadata ---\n{meta_json}"
                )
            except (TypeError, ValueError):
                sql_for_store = sql_stored

        # Store in OpenSearch
        try:
            stored = store_query(query, sql_for_store, doc_id=doc_id)
        except FeedbackProcessingError:
            raise
        except Exception as exc:
            raise FeedbackProcessingError(
                503, f"Failed to store in vector DB: {type(exc).__name__}"
            ) from exc

        if not stored:
            raise FeedbackProcessingError(
                503,
                "Could not index feedback. Check OPENAI_API_KEY and OpenSearch."
            )

        return FeedbackResponse(status="stored_in_vector_db")

    # ── THUMBS DOWN ──────────────────────────────────────────────────────────
    if feedback_type == "down":
        doc_id = make_stable_cache_doc_id(query, sql_val)

        try:
            os_client = get_opensearch_client()

            if os_client and os_client.exists(
                index=config.OPENSEARCH_INDEX_NAME, id=doc_id
            ):
                # Previously thumbs-up → remove from OpenSearch
                os_client.delete(
                    index=config.OPENSEARCH_INDEX_NAME, id=doc_id
                )
                entry = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "label": "REMOVED_FROM_VECTOR_DB",
                    "query": query,
                    "sql": sql_val or "",
                    "ai_response": response or "",
                    "feedback_type": "down",
                    "session_id": session_id,
                    "note": "Previously thumbs-up, now removed by thumbs-down"
                }
            else:
                # Never stored → just log as negative feedback
                entry = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "label": "NEGATIVE_FEEDBACK",
                    "query": query,
                    "sql": sql_val or "",
                    "ai_response": response or "",
                    "feedback_type": "down",
                    "session_id": session_id
                }

        except Exception:
            # OpenSearch check failed → fallback to just logging
            entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "label": "NEGATIVE_FEEDBACK",
                "query": query,
                "sql": sql_val or "",
                "ai_response": response or "",
                "feedback_type": "down",
                "session_id": session_id
            }

        log_feedback_to_file(entry)
        return FeedbackResponse(status="logged")

    # ── NO FEEDBACK or UNKNOWN ────────────────────────────────────────────────
    label = "NO_FEEDBACK" if feedback_type == "none" else "UNKNOWN_FEEDBACK"
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "label": label,
        "query": query,
        "sql": sql_val or "",
        "ai_response": response or "",
        "feedback_type": feedback_type,
        "session_id": session_id
    }
    log_feedback_to_file(entry)
    return FeedbackResponse(status="logged")


# ── FastAPI Router ───────────────────────────────────────────────────────────

feedback_router = APIRouter(tags=["Feedback"])


@feedback_router.post("/feedback", response_model=FeedbackResponse)
async def post_feedback(body: FeedbackRequest) -> FeedbackResponse:
    """
    Record user feedback.
    Only explicit thumbs-up stores in semantic cache (OpenSearch).
    Everything else is logged to file only.
    """
    try:
        return await asyncio.to_thread(submit_feedback, body)
    except FeedbackProcessingError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc