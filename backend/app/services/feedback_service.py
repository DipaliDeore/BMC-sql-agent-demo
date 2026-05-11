from __future__ import annotations
import asyncio
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

# pyrefly: ignore [missing-import]
from fastapi import APIRouter, HTTPException
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, ConfigDict, Field

from app import config
from app.opensearch_client import get_opensearch_client
from app.store import make_stable_cache_doc_id, store_query
# ── Helper: Thread-safe feedback logging ─────────────────────────────────────

def log_feedback_to_file(entry: dict):
    """
    Append feedback entry to feedback_logs.jsonl
    One JSON object per line (JSONL format)
    File location: backend/logs/feedback_logs.jsonl
    Create directory if not exists
    Thread-safe writing using file lock
    """
    import os, json
    from pathlib import Path
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "feedback_logs.jsonl"
    lock_file = log_dir / "feedback_logs.lock"
    # Use a file lock for thread safety
    lock = threading.Lock()
    with lock:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
"""
feedback_service.py — Thumbs feedback: semantic cache (vector DB) or file logging.

Routing (strict):
  * Only feedback == "up" (case-insensitive, after strip) → OpenSearch via store_query.
  * feedback in ("down", "none"), missing, empty, or any other value → logs/feedback.log only;
    vector helpers are not called.
"""


# ── Paths: logs/ at repository root (parent of backend/) ─────────────────────

_FEEDBACK_LOG_LOCK = threading.Lock()


def _repo_root() -> Path:
    """backend/app/services/this_file.py → repo root."""
    return Path(__file__).resolve().parents[3]


def _feedback_log_path() -> Path:
    return _repo_root() / "logs" / "feedback.log"


def _ensure_logs_dir() -> Path:
    path = _feedback_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _append_feedback_log_line(payload: dict[str, Any]) -> None:
    """Append one JSON object per line; UTF-8, process-safe."""
    log_path = _ensure_logs_dir()
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    try:
        with _FEEDBACK_LOG_LOCK:
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write(line)
    except OSError as exc:
        raise FeedbackProcessingError(
            500, f"Could not write feedback log: {exc}"
        ) from exc


def _feedback_log_label(raw: Any) -> str:
    """
    Human-readable feedback value for the log line (not used for routing).

    Missing / empty → "missing"; known tokens normalized to lowercase;
    otherwise the trimmed string as provided (invalid values preserved).
    """
    if raw is None:
        return "missing"
    text = str(raw).strip()
    if not text:
        return "missing"
    low = text.lower()
    if low in ("up", "down", "none"):
        return low
    return text


def _is_thumbs_up(raw: Any) -> bool:
    """True only for explicit thumbs-up; everything else is log-only."""
    if raw is None:
        return False
    return str(raw).strip().lower() == "up"


def _coerce_optional_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


# ── API models ────────────────────────────────────────────────────────────────


class FeedbackRequest(BaseModel):
    """POST /feedback body. ``feedback`` may be omitted (logged as missing, never vector)."""

    model_config = ConfigDict(extra="ignore")

    query: str = Field(default="", max_length=50_000)
    response: str = Field(default="", max_length=200_000)
    # When set, indexed as the OpenSearch ``sql`` field (validated SQL string only).
    sql: str = Field(default="", max_length=50_000)
    # Accept any JSON type from clients; normalize in submit_feedback.
    feedback: Any = None
    # Optional; when dict, included in log lines and appended for thumbs-up storage text.
    metadata: Any = None
    # Optional session_id for tracking user/session
    session_id: str | None = None


def _extract_sql_from_response(text: str) -> str:
    """
    Pull executed SQL from a combined assistant reply (narrative + SQL).

    Matches the common pattern: prose first, then a blank line, then ``SELECT``/``WITH``.
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


def _sql_for_vector_index(body: FeedbackRequest, response: str) -> str:
    """Prefer explicit ``sql``; else parse from ``response``; else empty."""
    explicit = _coerce_optional_str(body.sql)
    if explicit:
        return explicit
    return _extract_sql_from_response(response)


class FeedbackResponse(BaseModel):
    """POST /feedback success body."""

    status: Literal["stored_in_vector_db", "logged"]


class FeedbackProcessingError(Exception):
    """Raised from worker thread; converted to HTTPException in the route."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


# ── Core logic ────────────────────────────────────────────────────────────────


def submit_feedback(body: FeedbackRequest) -> FeedbackResponse:
    """
    Thumbs-up only → OpenSearch (embedding + store_query). All other outcomes → log file only.
    """
    query = (body.query or "").strip()
    response = (body.response or "").strip()
    sql_val = _coerce_optional_str(body.sql)
    session_id = body.session_id or "unknown"
    feedback_type = str(body.feedback).strip().lower() if body.feedback else "none"

    # Thumbs up: OpenSearch storage with duplicate check
    if _is_thumbs_up(body.feedback):
        if not query:
            raise FeedbackProcessingError(
                422,
                "Thumbs-up requires a non-empty query.",
            )
        sql_stored = _sql_for_vector_index(body, response)
        if not sql_stored:
            raise FeedbackProcessingError(
                422,
                "Thumbs-up requires SQL to index: send the ``sql`` field from the assistant turn, "
                "or include a SELECT/WITH statement in ``response``.",
            )

        client = get_opensearch_client()
        if client is None:
            raise FeedbackProcessingError(
                503,
                "Vector store is not available. Check OPENSEARCH_URL and that OpenSearch is running.",
            )

        index_name = config.OPENSEARCH_INDEX_NAME
        doc_id = make_stable_cache_doc_id(query, sql_stored)

        # Already in OpenSearch? Return early
        if client.exists(index=index_name, id=doc_id):
            return FeedbackResponse(status="stored_in_vector_db")

        sql_for_store = sql_stored
        if isinstance(body.metadata, dict) and body.metadata:
            try:
                meta_json = json.dumps(body.metadata, ensure_ascii=False, sort_keys=True)
                sql_for_store = f"{sql_stored}\n\n--- feedback_metadata ---\n{meta_json}"
            except (TypeError, ValueError):
                sql_for_store = sql_stored

        try:
            stored = store_query(query, sql_for_store, doc_id=doc_id)
        except FeedbackProcessingError:
            raise
        except Exception as exc:
            raise FeedbackProcessingError(
                503, f"Failed to store feedback in vector database: {type(exc).__name__}"
            ) from exc

        if not stored:
            raise FeedbackProcessingError(
                503,
                "Could not index feedback (embedding or OpenSearch error). "
                "Check OPENAI_API_KEY and OpenSearch connectivity.",
            )

        return FeedbackResponse(status="stored_in_vector_db")

    # Thumbs down: log to file and remove from OpenSearch if present
    if feedback_type == "down":
        doc_id = make_stable_cache_doc_id(query, sql_val)
        try:
            os_client = get_opensearch_client()
            if os_client and os_client.exists(
                index=config.OPENSEARCH_INDEX_NAME,
                id=doc_id
            ):
                # Remove from OpenSearch — user changed mind
                os_client.delete(
                    index=config.OPENSEARCH_INDEX_NAME,
                    id=doc_id
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

    # No feedback: log to file
    if feedback_type == "none":
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "label": "NO_FEEDBACK",
            "query": query,
            "sql": sql_val or "",
            "ai_response": response or "",
            "feedback_type": "none",
            "session_id": session_id
        }
        log_feedback_to_file(entry)
        return FeedbackResponse.model_validate({"status": "logged", "label": "NO_FEEDBACK"})

    # For any other feedback type, just log as before (fallback)
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "label": "UNKNOWN_FEEDBACK",
        "query": query,
        "sql": sql_val or "",
        "ai_response": response or "",
        "feedback_type": feedback_type,
        "session_id": session_id
    }
    log_feedback_to_file(entry)
    return FeedbackResponse.model_validate({"status": "logged", "label": "UNKNOWN_FEEDBACK"})


# ── Router (mounted at app root as POST /feedback) ────────────────────────────

feedback_router = APIRouter(tags=["Feedback"])


@feedback_router.post("/feedback", response_model=FeedbackResponse)
async def post_feedback(body: FeedbackRequest) -> FeedbackResponse:
    """Record user feedback; only explicit thumbs-up uses the semantic cache."""
    try:
        return await asyncio.to_thread(submit_feedback, body)
    except FeedbackProcessingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
