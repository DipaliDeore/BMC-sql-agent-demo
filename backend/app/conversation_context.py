"""
conversation_context.py — Build compact prior-turn context from chat_store for follow-ups.

Vision/image answers persist in chat_store but skip LangGraph checkpoints; this block
is injected into the agent system prompt so follow-ups like "explain the chart above" work.
"""

from __future__ import annotations

import json
from typing import Any

from app import chat_store

MAX_PRIOR_MESSAGES = 8
MAX_RESULT_ROWS_IN_CONTEXT = 20
MAX_CONTEXT_CHARS = 12_000


def _normalize_payload(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, str):
        try:
            o = json.loads(payload)
            return o if isinstance(o, dict) else {}
        except json.JSONDecodeError:
            return {}
    return payload if isinstance(payload, dict) else {}


def _format_results(rows: list[Any], *, max_rows: int = MAX_RESULT_ROWS_IN_CONTEXT) -> str:
    if not rows:
        return "(no rows)"
    lines: list[str] = []
    for i, row in enumerate(rows[:max_rows]):
        if isinstance(row, dict):
            lines.append(json.dumps(row, default=str, ensure_ascii=False))
        else:
            lines.append(str(row))
    if len(rows) > max_rows:
        lines.append(f"... ({len(rows) - max_rows} more rows omitted)")
    return "\n".join(lines)


def format_message_for_context(msg: dict[str, Any]) -> str:
    """Format one stored chat row for the prior-context block."""
    role = (msg.get("role") or "").strip().lower()
    content = (msg.get("content") or "").strip()
    payload = _normalize_payload(msg.get("payload"))

    if role == "user":
        return f"User: {content or '(no text)'}"

    if role != "assistant":
        return ""

    parts = [f"Assistant: {content or '(no text)'}"]
    if payload.get("error"):
        err = (payload.get("errorText") or content or "error").strip()
        parts.append(f"  (error: {err})")
        return "\n".join(parts)

    sql = (payload.get("sql") or "").strip()
    if sql:
        parts.append(f"  SQL executed: {sql}")

    rk = payload.get("response_kind")
    if rk:
        parts.append(f"  response_kind: {rk}")

    chart = payload.get("chart_config")
    if isinstance(chart, dict) and chart:
        parts.append(
            "  Chart shown in UI: "
            + json.dumps(chart, ensure_ascii=False)
        )

    row_count = payload.get("row_count")
    results = payload.get("results")
    if isinstance(results, list) and results:
        n = row_count if isinstance(row_count, int) else len(results)
        parts.append(f"  Result rows ({n}):")
        parts.append(_format_results(results))
    elif row_count is not None:
        parts.append(f"  row_count: {row_count}")

    return "\n".join(parts)


def build_context_from_messages(
    messages: list[dict[str, Any]],
    *,
    exclude_trailing_user: bool = True,
) -> str:
    """
    Build a prior-context string from stored messages (newest context last).

    When ``exclude_trailing_user`` is True, drops the last message if it is a user
    message (the turn currently being processed).
    """
    working = list(messages or [])
    if exclude_trailing_user and working and (working[-1].get("role") or "").lower() == "user":
        working = working[:-1]
    if not working:
        return ""

    tail = working[-MAX_PRIOR_MESSAGES:]
    blocks: list[str] = []
    for msg in tail:
        block = format_message_for_context(msg)
        if block:
            blocks.append(block)

    if not blocks:
        return ""

    text = "\n\n".join(blocks)
    if len(text) > MAX_CONTEXT_CHARS:
        text = text[: MAX_CONTEXT_CHARS - 24].rstrip() + "\n… [context truncated]"
    return text


def build_context_for_agent(
    chat_id: str,
    *,
    current_question: str | None = None,
) -> str:
    """Load chat history from ``chat_store`` and return the prior-context block."""
    if not (chat_id or "").strip():
        return ""
    _ = current_question  # reserved for future matching; trailing user is always dropped
    try:
        messages = chat_store.list_messages(chat_id.strip())
    except Exception as exc:
        print(f"[conversation_context] list_messages failed: {exc}")
        return ""
    return build_context_from_messages(messages, exclude_trailing_user=True)
