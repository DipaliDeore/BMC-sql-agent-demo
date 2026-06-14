from __future__ import annotations

import json
import logging
from collections.abc import Sequence

# pyrefly: ignore [missing-import]
from langchain_core.messages import BaseMessage, ToolMessage, AIMessage
# pyrefly: ignore [missing-import]
from langchain_core.runnables import RunnableConfig

from app import config
from app.memory.summary import (
    extract_user_assistant_snippets,
    generate_conversation_summary,
)
from app.memory.structured import extract_structured_memory, merge_structured_memory
from app.memory.tokens import estimate_messages_tokens
from app.memory.tool_digest import compress_tool_message_content
from app.memory.trim import last_human_message_index, trim_recent_messages
from app.thread_memory import get_thread_memory_row, upsert_thread_memory

logger = logging.getLogger(__name__)


def _digest_tools_before_last_user(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    u = last_human_message_index(messages)
    out: list[BaseMessage] = []
    for i, m in enumerate(messages):
        if isinstance(m, ToolMessage) and u >= 0 and i < u:
            out.append(compress_tool_message_content(m))
        else:
            out.append(m)
    return out


def apply_hybrid_message_view(
    raw_messages: Sequence[BaseMessage],
    runnable_config: RunnableConfig,
) -> list[BaseMessage]:
    """
    Non-destructive view for the LLM: digest old tool payloads, keep recent tail.
    Checkpointed state remains full raw_messages.
    """
    if not getattr(config, "HYBRID_MEMORY_ENABLED", False):
        return list(raw_messages)

    tid = (runnable_config.get("configurable") or {}).get("thread_id") or ""
    fresh = bool((runnable_config.get("configurable") or {}).get("fresh_data_query"))
    if fresh:
        u = last_human_message_index(raw_messages)
        if u >= 0:
            return _sanitize_tool_call_sequences([raw_messages[u]])
        return _sanitize_tool_call_sequences(list(raw_messages)[-1:])

    cap = int(getattr(config, "RECENT_MESSAGE_CAP", 30) or 30)

    processed = _digest_tools_before_last_user(raw_messages)
    tail = trim_recent_messages(processed, cap)

    est = estimate_messages_tokens(tail)
    soft = int(getattr(config, "MAX_CONTEXT_TOKENS_SOFT", 120000))
    if est > soft:
        logger.info(
            "memory.tokens_est thread_id=%s estimate=%s soft_limit=%s",
            tid,
            est,
            soft,
        )
        u2 = last_human_message_index(processed)
        tighter: list[BaseMessage] = []
        for i, m in enumerate(processed):
            if isinstance(m, ToolMessage) and u2 >= 0 and i <= u2:
                tighter.append(compress_tool_message_content(m))
            else:
                tighter.append(m)
        tail = trim_recent_messages(tighter, max(10, cap // 2))

    logger.info(
        "memory.trim thread_id=%s before=%s after=%s cap=%s",
        tid,
        len(raw_messages),
        len(tail),
        cap,
    )
    return _sanitize_tool_call_sequences(tail)

def _sanitize_tool_call_sequences(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    """
    Remove tool_calls from AIMessages if they are not followed by ToolMessages.
    This prevents Gemini's INVALID_ARGUMENT error when conversation history contains
    aborted or orphaned tool calls (e.g. from hitting recursion limits).
    """
    out: list[BaseMessage] = []
    for i, msg in enumerate(messages):
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            has_tool_response = False
            if i + 1 < len(messages) and isinstance(messages[i+1], ToolMessage):
                has_tool_response = True
            
            if not has_tool_response:
                # Strip the tool_calls from this message
                sanitized_msg = AIMessage(
                    content=msg.content,
                    id=msg.id,
                )
                out.append(sanitized_msg)
                continue
        out.append(msg)
    return out


def _system_memory_blocks(thread_id: str) -> tuple[str, str]:
    row = get_thread_memory_row(thread_id)
    summary = (row.get("conversation_summary") or "").strip()
    struct = row.get("structured_memory") or {}
    cap_s = getattr(config, "SUMMARY_MAX_CHARS", 8000)
    if len(summary) > cap_s:
        summary = summary[:cap_s] + "…"
    try:
        sj = json.dumps(struct, ensure_ascii=False, default=str)
    except Exception:
        sj = "{}"
    cap_j = getattr(config, "STRUCTURED_MEMORY_JSON_MAX_CHARS", 4000)
    if len(sj) > cap_j:
        sj = sj[:cap_j] + "…"
    return summary, sj


def build_memory_preamble_for_system(
    thread_id: str,
    *,
    fresh_data_query: bool = False,
) -> str:
    """Sections appended inside the main system string."""
    if fresh_data_query or not getattr(config, "HYBRID_MEMORY_ENABLED", False):
        return ""
    summary, sj = _system_memory_blocks(thread_id)
    parts: list[str] = []
    if sj and sj not in ("{}", "null"):
        parts.append("--- STRUCTURED_MEMORY_JSON ---\n" + sj)
    if summary:
        parts.append("--- CONVERSATION_SUMMARY (older turns; latest messages follow) ---\n" + summary)
    if not parts:
        return ""
    return "\n\n" + "\n\n".join(parts)


def maybe_refresh_thread_memory_after_turn(thread_id: str, messages: list[BaseMessage]) -> None:
    """
    After a completed graph turn: optionally update rolling summary + structured memory.
    Debounced to avoid an LLM call every request.
    """
    if not getattr(config, "HYBRID_MEMORY_ENABLED", False):
        return
    if not thread_id or not messages:
        return
    n = len(messages)
    trigger = int(getattr(config, "SUMMARY_TRIGGER_MESSAGES", 60))
    cap = int(getattr(config, "RECENT_MESSAGE_CAP", 30))
    debounce = int(getattr(config, "MEMORY_SUMMARY_DEBOUNCE_MESSAGES", 8))

    row = get_thread_memory_row(thread_id)
    last_ct = int(row.get("last_summarized_at_message_count") or 0)

    if n < trigger:
        return
    if n - last_ct < debounce:
        return

    if n <= cap:
        return
    old_slice = messages[:-cap]
    if not old_slice:
        return

    digest_old = _digest_tools_before_last_user(old_slice)
    prior_summary = row.get("conversation_summary") or ""
    prior_struct = dict(row.get("structured_memory") or {})

    try:
        new_summary = generate_conversation_summary(digest_old, prior_summary)
        snippet = extract_user_assistant_snippets(messages, max_msgs=40)
        delta_struct = extract_structured_memory(snippet, prior_struct)
        merged_struct = merge_structured_memory(prior_struct, delta_struct)
        upsert_thread_memory(
            thread_id,
            conversation_summary=new_summary,
            structured_memory=merged_struct,
            last_summarized_at_message_count=n,
        )
        logger.info(
            "memory.summary thread_id=%s input_msgs=%s out_summary_chars=%s",
            thread_id,
            len(old_slice),
            len(new_summary or ""),
        )
    except Exception as e:
        logger.warning("memory.summary_failed thread_id=%s err=%s", thread_id, e)
