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
"""

import asyncio
import functools
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from langsmith import traceable

from app import config
from app.fast_sql_pipeline import run_fast_sql_pipeline
from app.database import execute_query, get_database_schema
from app.query_analyzer import analyze_query
from app.sql_generator import is_dangerous_input
from app.query_validator import validate_sql, QueryValidationError
from app.search import REFERENCE_TOP_K, find_similar_queries
from app.agent_executor import generate_and_execute_with_tools
from app.store import store_query
from app import chat_store


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
    }


def _run_sql_agent(
    question: str,
    schema: str,
    references: list | None,
    *,
    thread_id: str | None = None,
) -> dict:
    """One-shot pipeline by default; LangGraph agent when USE_FAST_SQL_PIPELINE is false."""
    if config.USE_FAST_SQL_PIPELINE:
        return run_fast_sql_pipeline(
            question, schema, references, thread_id=thread_id
        )
    return generate_and_execute_with_tools(
        question, schema, references, thread_id=thread_id
    )


def _is_safe_reference(ex: dict) -> bool:
    """
    Return True if a cache reference row has SQL that passes the same
    validator used for the main pipeline (SELECT-only, etc.).
    """
    try:
        candidate_sql = (ex.get("sql") or "").strip()
        if not candidate_sql:
            return False
        validate_sql(candidate_sql)
        return True
    except QueryValidationError:
        return False


def _format_single_value(val) -> str:
    """Format a single value for display (no column names)."""
    if val is None:
        return "—"
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, (int, float)):
        return f"{val:,.2f}" if isinstance(val, float) else f"{val:,}"
    try:
        v = float(val)
        return f"{v:,.2f}" if v != int(v) else f"{int(v):,}"
    except (TypeError, ValueError):
        return str(val)


def _build_result_sentence(results: list[dict], answer_template: str | None = None) -> str | None:
    """Return a natural language sentence ONLY when result is a single value (1 row, 1 column)."""
    if not results or len(results) != 1:
        return None
    row = results[0]
    if not row or len(row) != 1:
        return None
    val = next(iter(row.values()))
    formatted = _format_single_value(val)
    if answer_template and "{}" in answer_template:
        try:
            return answer_template.replace("{}", formatted, 1)
        except Exception:
            pass
    return f"The result is {formatted}."


# Plain-language phrases for common aggregate column names (demo schema)
_RESULT_COLUMN_PHRASES: dict[str, str] = {
    "total_overall": "total sales overall",
    "total_january": "total sales in January",
    "total_february": "total sales in February",
    "total_march": "total sales in March",
    "total_amount": "total amount",
    "order_count": "number of orders",
    "customer_count": "number of customers",
}


def _metric_phrase_for_column(key: str) -> str:
    """Turn a result column name into a short phrase for sentences (lowercase)."""
    raw = (key or "").strip()
    kl = raw.lower()
    if kl in _RESULT_COLUMN_PHRASES:
        return _RESULT_COLUMN_PHRASES[kl]
    # Strip common SQL aggregate wrappers from labels
    label = raw
    for prefix in ("SUM(", "AVG(", "COUNT(", "MIN(", "MAX("):
        if label.upper().startswith(prefix):
            label = label[len(prefix) :]
            break
    label = label.replace(")", "").replace("(", " ").strip() or raw
    return label.replace("_", " ").strip().lower()


def _build_results_narrative(results: list[dict]) -> str | None:
    """
    Human-readable summary grounded in actual cell values (for chat + LangSmith clarity).
    Single row with multiple metrics -> simple sentences; many rows -> short intro pointing to table.
    """
    if not results:
        return None
    if len(results) > 1:
        return f"I found {len(results)} rows — the table below has the details."

    row = results[0]
    if not row:
        return None
    if len(row) < 2:
        return None

    sentences: list[str] = []
    for key, val in row.items():
        phrase = _metric_phrase_for_column(key)
        formatted = _format_single_value(val)
        sentences.append(f"The {phrase} is {formatted}.")

    body = " ".join(sentences)
    return f"Here's what the data shows:\n\n{body}"


def _merge_explanation_with_narrative(llm_explanation: str, narrative: str | None) -> str:
    """Put numeric facts first; keep the model's friendly context after."""
    llm = (llm_explanation or "").strip()
    if not narrative:
        return llm
    generic_llm = llm.lower() in (
        "",
        "query executed successfully.",
        "here's what i pulled.",
        "got it!",
    )
    if generic_llm or not llm:
        return narrative
    return f"{narrative}\n\n{llm}"





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

    pref = (body.preference or "AUTO").upper()
    loop = asyncio.get_running_loop()

    # The LangGraph Agent now natively handles MULTI query parallelization.
    # Therefore, we always bypass analyze_query and use the unified pipeline.
    analysis = {"type": "SINGLE", "queries": [body.question]}
    similar_examples_raw = await loop.run_in_executor(None, find_similar_queries, body.question, REFERENCE_TOP_K)

    # ── Unified path (SINGLE logic native multi tool-calling) ───────
    if analysis["type"] == "SINGLE":
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

        tool_result = _run_sql_agent(
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

        # Fire-and-forget: store in OpenSearch after response — doc id is known up front for cache_doc_id.
        cache_doc_id = str(uuid.uuid4())
        loop.run_in_executor(
            None,
            functools.partial(store_query, body.question, safe_sql, cache_doc_id),
        )
        row_count = len(result)

        narrative = _build_results_narrative(result)
        explanation = _merge_explanation_with_narrative(explanation, narrative)

        return QueryResponse(
            question=body.question,
            sql=safe_sql,
            results=result,
            explanation=explanation,
            row_count=row_count,
            result_sentence=_build_result_sentence(result, answer_template),
            cache_references=filtered_examples or None,
            conversation_id=conversation_id,
            cache_doc_id=cache_doc_id,
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