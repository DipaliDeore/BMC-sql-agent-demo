"""
Server-Sent Events (SSE) streaming for POST /api/query/stream.

Data flow (USE_FAST_SQL_PIPELINE=false):
  Client → FastAPI → LangGraph ``stream`` on a worker thread (sync checkpointer;
  ``astream`` requires ``aget_tuple``, which sync ``PostgresSaver`` does not implement)
  with ``stream_mode`` messages + values → SSE chunks
  (status / token / sql / data) → final JSON → chat_store.

Fast pipeline (USE_FAST_SQL_PIPELINE=true) — **Option A**:
  Stream LLM tokens from the SQL LangGraph ``generate`` node, then run
  ``run_fast_sql_pipeline_after_gen`` with per-row callbacks for ``data`` events.
"""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
import functools
from typing import Any, AsyncIterator

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from app import chat_store, config
from app.agent_executor import (
    _build_references_text,
    _get_agent_app,
    _parse_tool_content,
    _summarize_from_messages,
)
from app.database import get_database_schema
from app.query_validator import QueryValidationError, validate_sql, is_dangerous_input
from app.response_formatting import (
    build_result_sentence,
    build_results_narrative,
    merge_explanation_with_narrative,
)
from app.search import REFERENCE_TOP_K, find_similar_queries
def _sse_data(obj: dict) -> bytes:
    line = json.dumps(obj, default=str)
    return f"data: {line}\n\n".encode("utf-8")


def encode_sse(obj: dict) -> bytes:
    """Public alias for SSE framing (used by routes for one-shot streams)."""
    return _sse_data(obj)

def _rate_limited(e: Exception) -> bool:
    error_str = str(e).lower()
    return any(k in error_str for k in ("429", "resource_exhausted", "quota"))


def _text_delta_from_llm_chunk(msg: Any) -> str:
    if not isinstance(msg, AIMessageChunk):
        return ""
    c = msg.content
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts: list[str] = []
        for block in c:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text" and block.get("text"):
                    parts.append(str(block["text"]))
        return "".join(parts)
    return ""


def _seen_tool_signature(m: ToolMessage) -> str:
    tid = getattr(m, "tool_call_id", "") or ""
    raw = m.content
    if isinstance(raw, str):
        return f"{tid}:{raw[:200]}"
    return f"{tid}:{hash(str(raw))}"


async def _async_iter_sync_graph_stream(
    graph: Any,
    inputs: dict[str, Any],
    cfg: dict[str, Any],
    *,
    stream_mode: list[str],
) -> AsyncIterator[Any]:
    """
    Consume ``graph.stream(...)`` from a worker thread.

    LangGraph's ``astream`` uses ``checkpointer.aget_tuple``; sync ``PostgresSaver`` only
    implements ``get_tuple``, so async streaming would raise ``NotImplementedError``.
    """
    loop = asyncio.get_running_loop()
    q: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    def _worker() -> None:
        try:
            for chunk in graph.stream(inputs, cfg, stream_mode=stream_mode):
                asyncio.run_coroutine_threadsafe(q.put(("c", chunk)), loop).result(timeout=600)
        except BaseException as exc:
            try:
                asyncio.run_coroutine_threadsafe(q.put(("e", exc)), loop).result(timeout=60)
            except Exception:
                pass
        finally:
            try:
                asyncio.run_coroutine_threadsafe(q.put(("d", None)), loop).result(timeout=60)
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True).start()
    while True:
        tag, payload = await q.get()
        if tag == "d":
            break
        if tag == "e":
            raise payload
        yield payload


async def _stream_react_agent(
    question: str,
    schema: str,
    references: list[dict] | None,
    thread_id: str,
    cfg_recursion: int = 12,
) -> AsyncIterator[dict[str, Any]]:
    app = _get_agent_app()
    references_text = _build_references_text(references or [])
    runnable_cfg: dict[str, Any] = {
        "configurable": {
            "thread_id": thread_id,
            "schema": schema,
            "references_text": references_text,
        },
        "recursion_limit": cfg_recursion,
    }

    yield {"type": "status", "content": "thinking"}

    prev_len = 0
    processed_tool_sigs: set[str] = set()
    emitted_pre_sql: set[str] = set()
    last_values: dict[str, Any] | None = None

    try:
        stream_iter = _async_iter_sync_graph_stream(
            app,
            {"messages": [HumanMessage(content=question.strip())]},
            runnable_cfg,
            stream_mode=["messages", "values"],
        )
        async for chunk in stream_iter:
            if not isinstance(chunk, tuple) or len(chunk) != 2:
                continue
            mode, payload = chunk
            if mode == "messages":
                if isinstance(payload, tuple) and len(payload) >= 1:
                    token_msg = payload[0]
                else:
                    token_msg = payload
                text = _text_delta_from_llm_chunk(token_msg)
                if text:
                    yield {"type": "token", "content": text}
            elif mode == "values":
                last_values = payload or {}
                msgs = (payload or {}).get("messages") or []
                if len(msgs) <= prev_len:
                    continue
                new_msgs = msgs[prev_len:]
                prev_len = len(msgs)
                for m in new_msgs:
                    if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
                        for tc in m.tool_calls:
                            if tc.get("name") != "run_sql_query":
                                continue
                            args = tc.get("args") or {}
                            sql = (args.get("sql") or "").strip()
                            if not sql:
                                continue
                            tid = tc.get("id") or sql[:120]
                            key = f"pre:{tid}"
                            if key in emitted_pre_sql:
                                continue
                            emitted_pre_sql.add(key)
                            yield {"type": "status", "content": "executing_sql"}
                            yield {"type": "sql", "content": sql}
                    if isinstance(m, ToolMessage):
                        sig = _seen_tool_signature(m)
                        if sig in processed_tool_sigs:
                            continue
                        processed_tool_sigs.add(sig)
                        data = _parse_tool_content(m)
                        if data.get("success") and isinstance(data.get("results"), list):
                            for row in data["results"]:
                                yield {"type": "data", "content": row}
    except Exception as e:
        if _rate_limited(e):
            yield {
                "type": "error",
                "content": "The AI service quota has been reached. Please wait a few minutes or try again later.",
            }
            return
        yield {"type": "error", "content": str(e) or "Agent stream failed."}
        return

    messages: list[Any] = []
    try:
        snap = await asyncio.to_thread(app.get_state, runnable_cfg)
        values = getattr(snap, "values", None) or {}
        messages = values.get("messages") or []
    except Exception:
        messages = []
    if not messages and last_values is not None:
        messages = last_values.get("messages") or []

    summary = _summarize_from_messages(messages)
    yield {"type": "status", "content": "done"}
    yield {"type": "final", "content": summary}





def _filter_safe_references(raw: list[dict]) -> list[dict]:
    filtered: list[dict] = []
    for ex in raw:
        try:
            candidate_sql = (ex.get("sql") or "").strip()
            if candidate_sql:
                validate_sql(candidate_sql)
                filtered.append(ex)
        except QueryValidationError:
            continue
    return filtered


def _final_http_payload_from_tool_result(
    question: str,
    conversation_id: str,
    tool_result: dict[str, Any],
    cache_refs: list[dict] | None,
    assistant_message_id: str | None = None,
) -> dict[str, Any]:
    """Shape aligned with QueryResponse / chat_store assistant payload."""
    sql = (tool_result.get("sql_query") or "").strip()
    results = tool_result.get("results") or []
    explanation = (tool_result.get("explanation") or "").strip()
    row_count = int(tool_result.get("row_count") or 0)
    answer_template = tool_result.get("answer_template")

    narrative = build_results_narrative(results) if results else None
    explanation_out = merge_explanation_with_narrative(explanation, narrative)

    return {
        "question": question,
        "conversation_id": conversation_id,
        "sql": sql,
        "results": results,
        "explanation": explanation_out,
        "row_count": row_count,
        "result_sentence": build_result_sentence(results, answer_template),
        "cache_references": cache_refs,
        "is_multi": bool(tool_result.get("is_multi")),
        "sub_responses": tool_result.get("sub_responses") or [],
        "is_ambiguous": False,
        "cache_doc_id": tool_result.get("cache_doc_id"),
        "assistant_message_id": assistant_message_id,
        "chart_config": tool_result.get("chart_config"),
    }


def _chat_assistant_content(final: dict[str, Any]) -> str:
    ex = (final.get("explanation") or "").strip()
    return ex if ex else "Done."


def _chat_payload_from_final(final: dict[str, Any]) -> dict[str, Any]:
    return {
        "sql": final.get("sql") or "",
        "results": final.get("results") or [],
        "explanation": final.get("explanation") or "",
        "row_count": final.get("row_count") or 0,
        "result_sentence": final.get("result_sentence"),
        "cache_references": final.get("cache_references"),
        "is_multi": final.get("is_multi", False),
        "sub_responses": final.get("sub_responses") or [],
        "is_ambiguous": final.get("is_ambiguous", False),
        "cache_doc_id": final.get("cache_doc_id"),
        "chart_config": final.get("chart_config"),
    }


def _materialize_http_final(
    question: str,
    conversation_id: str,
    tool_result: dict[str, Any],
    cache_refs: list[dict] | None,
) -> dict[str, Any]:
    """Apply the same post-processing as the non-streaming query path (cache, narratives)."""
    tr = dict(tool_result)
    status = tr.get("status")

    if status == "sql_error":
        tr["explanation"] = "Sorry, could not generate a valid query. Please try rephrasing."

    if status == "success" and not (tr.get("results") or []):
        tr["explanation"] = "I ran the query but nothing matched. Try broadening your filters."

    # Semantic cache writes only via POST /feedback (thumbs up); do not auto-index stream replies.
    final = _final_http_payload_from_tool_result(
        question,
        conversation_id,
        tr,
        cache_refs,
        assistant_message_id=None,
    )
    final["cache_doc_id"] = None
    return final


async def streaming_query_handler(body: Any) -> AsyncIterator[bytes]:
    """
    Async byte iterator for ``StreamingResponse`` (SSE).
    ``body`` matches ``QueryRequest`` from routes (validated there).

    Inner generators may emit ``{"type": "final", "content": <tool dict>}``; this handler
    buffers that event and emits a single HTTP-shaped ``final`` after ``chat_store`` persistence.
    """
    conversation_id = (getattr(body, "conversation_id", None) or "").strip() or str(uuid.uuid4())
    question = (body.question or "").strip()

    loop = asyncio.get_running_loop()

    if is_dangerous_input(question):
        final = {
            "question": question,
            "conversation_id": conversation_id,
            "sql": "",
            "results": [],
            "explanation": (
                "I can only look up data for you — I can't change or delete anything in the database. "
                "Try asking a read-only question (like counts, lists, or filters) and I'll help!"
            ),
            "row_count": 0,
            "result_sentence": None,
            "cache_references": None,
            "is_multi": False,
            "sub_responses": [],
            "is_ambiguous": False,
            "cache_doc_id": None,
            "assistant_message_id": None,
        }
        row = chat_store.add_message(
            conversation_id,
            "assistant",
            _chat_assistant_content(final),
            _chat_payload_from_final(final),
        )
        final["assistant_message_id"] = str(row["id"])
        yield _sse_data({"type": "status", "content": "done"})
        yield _sse_data({"type": "final", "content": final})
        return

    try:
        schema = await loop.run_in_executor(None, get_database_schema)
        similar_raw = await loop.run_in_executor(
            None,
            functools.partial(find_similar_queries, question, REFERENCE_TOP_K),
        )
    except Exception as e:
        err_text = str(e) or "Failed to load schema or references."
        yield _sse_data({"type": "error", "content": err_text})
        chat_store.add_message(
            conversation_id,
            "assistant",
            err_text,
            {"error": True, "errorText": err_text},
        )
        return

    cache_refs = _filter_safe_references(similar_raw or [])

    tool_result: dict[str, Any] | None = None

    try:
        stream = _stream_react_agent(question, schema, cache_refs or None, conversation_id)
        async for ev in stream:
            if ev.get("type") == "error":
                yield _sse_data(ev)
                err_text = (ev.get("content") or "Error").strip() or "Error"
                chat_store.add_message(
                    conversation_id,
                    "assistant",
                    err_text,
                    {"error": True, "errorText": err_text},
                )
                return
            if ev.get("type") == "final":
                tool_result = ev.get("content") if isinstance(ev.get("content"), dict) else None
                continue
            yield _sse_data(ev)
    except Exception as e:
        err_text = (str(e) or "").strip() or "Stream failed."
        yield _sse_data({"type": "error", "content": err_text})
        chat_store.add_message(
            conversation_id,
            "assistant",
            err_text,
            {"error": True, "errorText": err_text},
        )
        return

    if tool_result is None:
        err_text = "No final tool result produced."
        yield _sse_data({"type": "error", "content": err_text})
        chat_store.add_message(
            conversation_id,
            "assistant",
            err_text,
            {"error": True, "errorText": err_text},
        )
        return

    final = _materialize_http_final(question, conversation_id, tool_result, cache_refs or None)
    row = chat_store.add_message(
        conversation_id,
        "assistant",
        _chat_assistant_content(final),
        _chat_payload_from_final(final),
    )
    final["assistant_message_id"] = str(row["id"])
    yield _sse_data({"type": "final", "content": final})
