"""
routes.py - API Endpoints (Module 5)
-------------------------------------
This file is responsible for:
    - Defining all API endpoints for the SQL Agent Demo
    - Defining request/response models using Pydantic

Endpoints:
    GET  /api/test-db   — Test the database connection
    GET  /api/schema    — Return the database schema
    POST /api/query     — Ask a natural language question → get SQL + results + explanation
    POST /api/query/stream — Same pipeline as ``/api/query`` over SSE (tokens, status, rows, final JSON)

Also see ``app.services.feedback_service``: POST /feedback (thumbs up/down) at app root.
"""

import asyncio
import uuid
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, HTTPException
# pyrefly: ignore [missing-import]
from fastapi.responses import StreamingResponse
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field, field_validator
# pyrefly: ignore [missing-import]
from langsmith import traceable

import os
from pathlib import Path
# pyrefly: ignore [missing-import]
from fastapi.responses import FileResponse
from app.excel_export import generate_excel, should_offer_excel

from app import config
from app.database import execute_query, get_database_schema, select_sql_with_row_limit
from app.query_validator import validate_sql, QueryValidationError, is_dangerous_input
from app.search import REFERENCE_TOP_K, find_similar_queries
from app.agent_executor import generate_and_execute_with_tools
from app import chat_store
from app.response_formatting import (
    build_result_sentence,
    build_results_narrative,
    merge_explanation_with_narrative,
)


# ── Create API Router ─────────────────────────────────────────────────────────
# All routes defined here will automatically get the /api prefix.
# Example: "/query" becomes "/api/query"
router = APIRouter(prefix="/api", tags=["SQL Agent"])


# ── Request / Response Models ─────────────────────────────────────────────────

class ChatMessageItem(BaseModel):
    """One turn for client-synced conversation history (optional)."""

    role: str
    content: str

    @field_validator("role")
    @classmethod
    def _role_ok(cls, v: str) -> str:
        if v not in ("user", "assistant"):
            raise ValueError('role must be "user" or "assistant"')
        return v


class QueryRequest(BaseModel):
    """Request body for the POST /api/query endpoint."""
    question: str  # The user's natural language question
    # Stable id per chat; LangGraph thread + Postgres checkpoints recall prior turns
    conversation_id: str | None = None
    preference: str | None = "AUTO"  # "AUTO", "SINGLE", "MULTI"
    # Optional: full transcript from the client (stored server-side is authoritative)
    messages: list[ChatMessageItem] | None = None


class CreateChatBody(BaseModel):
    title: str | None = None


class RenameChatBody(BaseModel):
    title: str


class QueryResponse(BaseModel):
    """Response body for the POST /api/query endpoint."""
    question: str        # The original question echoed back
    sql: str             # The generated SQL query
    results: list[dict]  # Rows returned from the database
    explanation: str     # Plain-English explanation of the SQL query
    row_count: int       # Number of rows returned
    result_sentence: str | None = None  # Natural language sentence for single value (e.g. "Total number of customers are 10")
    # Optional debug info to show what semantic cache retrieval returned.
    # This does not affect the main logic.
    cache_references: list[dict] | None = None
    conversation_id: str | None = None  # Echo effective thread id — reuse on later requests
    is_ambiguous: bool = False  # Flag to prompt user for preference
    # Multi-query responses (optional; defaults keep single-query clients unchanged)
    is_multi: bool = False
    sub_responses: list[dict] = Field(default_factory=list)
    # OpenSearch document id for the (question, SQL) pair stored after success (semantic cache).
    cache_doc_id: str | None = None
    # DB id of the assistant row saved for this response.
    assistant_message_id: str | None = None
    # chart_type: pie | bar | line; x_column / y_column (+ optional y_column_2) = exact result keys (sql_tools)
    chart_config: dict | None = None
    excel_download_url: str | None = None


def _assistant_chat_content(resp: QueryResponse) -> str:
    ex = (resp.explanation or "").strip()
    if ex:
        return ex
    return "Done."


def _assistant_payload_from_response(resp: QueryResponse) -> dict:
    return {
        "sql": resp.sql,
        "results": resp.results,
        "explanation": resp.explanation,
        "row_count": resp.row_count,
        "result_sentence": resp.result_sentence,
        "cache_references": resp.cache_references,
        "is_multi": resp.is_multi,
        "sub_responses": resp.sub_responses,
        "is_ambiguous": resp.is_ambiguous,
        "cache_doc_id": resp.cache_doc_id,
        "chart_config": resp.chart_config,
        "excel_download_url": resp.excel_download_url,
    }


# ── Endpoint 1: Test Database Connection ──────────────────────────────────────

@router.get("/test-db")
async def test_db_connection():
    """
    Test the database connection.

    URL: GET /api/test-db
    Runs a simple SELECT query on the customers table and returns
    up to 3 rows so you can confirm connectivity.
    """
    result = execute_query("SELECT * FROM customers LIMIT 3")

    # execute_query returns {"error": "..."} if something went wrong
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(
            status_code=503,
            detail="I couldn't reach the database just now. Double-check it's running and try again?",
        )

    return {
        "message": "Database connection successful!",
        "rows_returned": len(result),
        "data": result
    }


# ── Endpoint 2: Get Database Schema ──────────────────────────────────────────

@router.get("/schema")
async def get_schema():
    """
    Return the database schema.

    URL: GET /api/schema
    The schema describes all tables, columns, and relationships.
    It is also used internally by the AI to generate correct SQL.
    """
    schema = get_database_schema()
    return {"schema": schema}


# ── Endpoint 3: Handle Natural Language Query ─────────────────────────────────


@traceable(name="sql_demo_query", run_type="chain")
async def _execute_nl_query(body: QueryRequest, conversation_id: str) -> QueryResponse:
    """
    Full NL → SQL pipeline. Wrapped in @traceable so LangSmith nests the query-analyzer
    RunnableSequence and the sql_react_agent / generator graph under one parent trace.
    """
    # ── Schema + multi-query analysis (must run before branching) ───────────────
    schema = get_database_schema()

    # Log-only length warning — do not reject long questions.
    if len(body.question) > config.MAX_QUERY_LENGTH:
        print(f"[WARN] Long query detected: {len(body.question)} chars")

    loop = asyncio.get_running_loop()
    similar_examples_raw = await loop.run_in_executor(None, find_similar_queries, body.question, REFERENCE_TOP_K)

    # Unified NL→SQL path (multi-query handled inside LangGraph via parallel tool calls).

    # Security: block destructive intent before any Gemini call (single input only).
    if is_dangerous_input(body.question):
        return QueryResponse(
            question=body.question,
            sql="",
            results=[],
            explanation="I can only look up data for you — I can't change or delete anything in the database. Try asking a read-only question (like counts, lists, or filters) and I'll help!",
            row_count=0,
            conversation_id=conversation_id,
        )

    # Semantic cache: OpenSearch similarity for reference examples in the prompt.
    # Results already fetched concurrently above — just filter for safety.
    filtered_examples: list[dict] = []
    for ex in similar_examples_raw:
        try:
            candidate_sql = (ex.get("sql") or "").strip()
            if candidate_sql:
                validate_sql(candidate_sql)
                filtered_examples.append(ex)
        except QueryValidationError:
            continue

    # Fast Path: bypass LLM if exact match is found
    if filtered_examples and filtered_examples[0].get("score", 0.0) >= 0.99:
        exact_match = filtered_examples[0]
        exact_sql = exact_match["sql"]
        db_res = execute_query(exact_sql)
        if not (isinstance(db_res, dict) and "error" in db_res):
            explanation = "I ran a matching query for your question and retrieved the results below."
            narrative = build_results_narrative(db_res)
            explanation = merge_explanation_with_narrative(explanation, narrative)
            
            return QueryResponse(
                question=body.question,
                sql=select_sql_with_row_limit(exact_sql),
                results=db_res,
                explanation=explanation,
                row_count=len(db_res),
                result_sentence=build_result_sentence(db_res, None),
                cache_references=filtered_examples or None,
                conversation_id=conversation_id,
                cache_doc_id=None,
                chart_config=None,
            )

    tool_result = generate_and_execute_with_tools(
        body.question,
        schema,
        filtered_examples or None,
        thread_id=conversation_id,
    )

    

    if tool_result["status"] == "db_error":
        return QueryResponse(
            question=body.question,
            sql="",
            results=[],
            row_count=0,
            explanation=tool_result["explanation"],
            conversation_id=conversation_id,
        )

    if tool_result["status"] == "not_related":
        return QueryResponse(
            question=body.question,
            sql="",
            results=[],
            row_count=0,
            explanation=tool_result["explanation"],
            conversation_id=conversation_id,
        )

    if tool_result["status"] == "sql_error":
        return QueryResponse(
            question=body.question,
            sql="",
            results=[],
            row_count=0,
            explanation="Sorry, could not generate a valid query. Please try rephrasing.",
            conversation_id=conversation_id,
        )

    if tool_result["status"] == "rate_limited":
        return QueryResponse(
            question=body.question,
            sql="",
            results=[],
            row_count=0,
            explanation=tool_result["explanation"],
            conversation_id=conversation_id,
        )

    if tool_result.get("is_multi"):
        return QueryResponse(
            question=body.question,
            sql="",
            results=[],
            explanation=tool_result["explanation"],
            row_count=0,
            conversation_id=conversation_id,
            is_multi=True,
            sub_responses=tool_result.get("sub_responses", []),
        )

    result = tool_result["results"]
    safe_sql = tool_result["sql_query"]
    explanation = tool_result["explanation"]
    answer_template = tool_result.get("answer_template")

    if not result:
        return QueryResponse(
            question=body.question,
            sql=safe_sql,
            results=[],
            row_count=0,
            explanation="I ran the query but nothing matched. Try broadening your filters.",
            conversation_id=conversation_id,
        )

    # Semantic cache writes only via POST /feedback (thumbs up); do not auto-index every reply.
    row_count = len(result)

    excel_download_url = None

    if row_count > 0 and should_offer_excel(result, body.question, row_count):
        try:
            filepath = generate_excel(result)
            filename = os.path.basename(filepath)
            excel_download_url = f"/api/export/{filename}"
        except Exception as e:
            print(f"[ExcelExport] Failed: {e}")
            excel_download_url = None

    inline_results = result if row_count <= config.EXCEL_INLINE_LIMIT else []

    narrative = build_results_narrative(result)
    explanation = merge_explanation_with_narrative(explanation, narrative)

    return QueryResponse(
        question=body.question,
        sql=safe_sql,
        results=inline_results,
        explanation=explanation,
        row_count=row_count,
        result_sentence=build_result_sentence(result, answer_template),
        cache_references=filtered_examples or None,
        conversation_id=conversation_id,
        cache_doc_id=None,
        chart_config=tool_result.get("chart_config"),
        excel_download_url=excel_download_url,
    )


@router.post("/query", response_model=QueryResponse)
async def handle_query(body: QueryRequest):
    """
    Accept a natural language question and return SQL + results + explanation.

    URL: POST /api/query

    Flow:
        1. Receive user question
        2. Get the DB schema (so the AI knows the table structure)
        3. Call Gemini to generate SQL + explanation
        4. Validate the SQL for safety (SELECT-only)
        5. Execute the SQL against the database
        6. Return question, sql, results, explanation, and row_count

    Edge Cases:
        - If Gemini returns empty SQL → return safely with empty results
        - If query returns no rows → explanation = "No records found for your query."
    """
    conversation_id = (body.conversation_id or "").strip() or str(uuid.uuid4())

    # Empty question — respond in chat style (still a normal JSON body for clients)
    if not body.question.strip():
        return QueryResponse(
            question=body.question,
            sql="",
            results=[],
            explanation="Hmm, I didn't quite catch that — could you ask that again with a bit more detail?",
            row_count=0,
            conversation_id=conversation_id,
        )

    # Client may send `messages` for sync; execution uses server store + LangGraph checkpoints.
    _ = body.messages

    chat_store.ensure_chat(conversation_id)
    chat_store.maybe_set_title_from_first_question(
        conversation_id, body.question.strip()
    )
    chat_store.add_message(conversation_id, "user", body.question.strip(), None)

    try:
        response = await _execute_nl_query(body, conversation_id)
    except Exception as e:
        err_text = (str(e) or "").strip() or "Something went wrong. Please try again."
        chat_store.add_message(
            conversation_id,
            "assistant",
            err_text,
            {"error": True, "errorText": err_text},
        )
        raise

    row = chat_store.add_message(
        conversation_id,
        "assistant",
        _assistant_chat_content(response),
        _assistant_payload_from_response(response),
    )
    return response.model_copy(update={"assistant_message_id": str(row["id"])})


@router.post("/query/stream")
async def handle_query_stream(body: QueryRequest):
    """
    SSE stream of NL→SQL progress (tokens, status, SQL, row chunks) and one HTTP-shaped ``final``.

    Does not change ``POST /api/query`` behavior.
    """
    from app.query_stream import encode_sse, streaming_query_handler

    conversation_id = (body.conversation_id or "").strip() or str(uuid.uuid4())
    body = body.model_copy(update={"conversation_id": conversation_id})

    if not body.question.strip():

        async def _empty_sse():
            final = {
                "question": body.question,
                "conversation_id": conversation_id,
                "sql": "",
                "results": [],
                "explanation": "Hmm, I didn't quite catch that — could you ask that again with a bit more detail?",
                "row_count": 0,
                "result_sentence": None,
                "cache_references": None,
                "is_multi": False,
                "sub_responses": [],
                "is_ambiguous": False,
                "cache_doc_id": None,
                "assistant_message_id": None,
                "chart_config": None,
            }
            yield encode_sse({"type": "status", "content": "done"})
            yield encode_sse({"type": "final", "content": final})

        return StreamingResponse(
            _empty_sse(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    _ = body.messages

    chat_store.ensure_chat(conversation_id)
    chat_store.maybe_set_title_from_first_question(
        conversation_id, body.question.strip()
    )
    chat_store.add_message(conversation_id, "user", body.question.strip(), None)

    return StreamingResponse(
        streaming_query_handler(body),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chats")
async def api_list_chats():
    return {"chats": chat_store.list_chats()}


@router.post("/chats")
async def api_create_chat(body: CreateChatBody | None = None):
    b = body if body is not None else CreateChatBody()
    return chat_store.create_chat(b.title)


@router.get("/chats/{chat_id}/messages")
async def api_get_chat_messages(chat_id: str):
    if chat_store.get_chat(chat_id) is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"messages": chat_store.list_messages(chat_id)}


@router.patch("/chats/{chat_id}")
async def api_rename_chat(chat_id: str, body: RenameChatBody):
    if not chat_store.rename_chat(chat_id, body.title):
        raise HTTPException(status_code=404, detail="Chat not found")
    row = chat_store.get_chat(chat_id)
    assert row is not None
    return row


@router.delete("/chats/{chat_id}")
async def api_delete_chat(chat_id: str):
    if chat_store.get_chat(chat_id) is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    chat_store.delete_chat(chat_id)
    return {"ok": True}

@router.get("/export/{filename}")
async def download_excel(filename: str):
    """Serve generated Excel file for download."""
    # Security: prevent path traversal
    if not filename.endswith(".xlsx") or "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    exports_dir = Path(__file__).parent.parent / "exports"
    filepath = exports_dir / filename

    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )