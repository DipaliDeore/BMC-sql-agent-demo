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
import re
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from langsmith import traceable

from app import config
from app.fast_sql_pipeline import run_fast_sql_pipeline
from app.database import execute_query, get_database_schema
from app.query_analyzer import analyze_query
from app.sql_generator import generate_sql_and_explanation, is_dangerous_input
from app.query_validator import validate_sql, QueryValidationError
from app.search import REFERENCE_TOP_K, find_similar_queries
from app.sql_retry_engine import execute_with_retry
from app.agent_executor import generate_and_execute_with_tools
from app.store import store_query


# ── Create API Router ─────────────────────────────────────────────────────────
# All routes defined here will automatically get the /api prefix.
# Example: "/query" becomes "/api/query"
router = APIRouter(prefix="/api", tags=["SQL Agent"])


# ── Fast-path helpers (zero LLM calls) ───────────────────────────────────────

_GREETING_PHRASES = frozenset({
    "hi", "hello", "hey", "howdy", "hiya", "sup", "greetings",
    "good morning", "good afternoon", "good evening", "good day",
    "how are you", "how are you doing", "how is it going",
    "hi there", "hello there", "hey there", "what's up", "whats up",
    "yo", "namaste", "helo", "hii", "hiii",
})


def _is_pure_greeting(question: str) -> bool:
    """Return True for pure greetings/small-talk — no DB question present."""
    q = re.sub(r"[^\w\s]", "", question.strip().lower())
    q = " ".join(q.split())
    return q in _GREETING_PHRASES


# Indicators that strongly suggest a multi-part question.
_MULTI_INDICATORS = (
    " and also ", " and also show ", " additionally ", " also show ",
    " also find ", " also give ", " as well as ", " separately ",
    " in addition", " furthermore", " moreover", " along with ",
    "1.", "2.", "1)", "2)",
)


def _is_clearly_single(question: str) -> bool:
    """Return True when no multi-query indicators are present — safe to skip LLM analysis."""
    q = question.lower()
    return not any(ind in q for ind in _MULTI_INDICATORS)


# ── Request / Response Models ─────────────────────────────────────────────────

class QueryRequest(BaseModel):
    """Request body for the POST /api/query endpoint."""
    question: str  # The user's natural language question
    # Stable id per browser session so LangGraph MemorySaver can recall prior turns
    conversation_id: str | None = None
    preference: str | None = "AUTO"  # "AUTO", "SINGLE", "MULTI"


class QueryResponse(BaseModel):
    """Response body for the POST /api/query endpoint."""
    question: str        # The original question echoed back
    sql: str             # The generated SQL query
    results: list[dict]  # Rows returned from the database
    explanation: str     # Plain-English explanation of the SQL query
    row_count: int       # Number of rows returned
    result_summary: str | None = None  # Deprecated: use result_sentence for single-value
    result_sentence: str | None = None  # Natural language sentence for single value (e.g. "Total number of customers are 10")
    # Optional debug info to show what Pinecone retrieval returned.
    # This does not affect the main logic.
    cache_references: list[dict] | None = None
    conversation_id: str | None = None  # Echo effective thread id — reuse on later requests
    is_ambiguous: bool = False  # Flag to prompt user for preference
    # Multi-query responses (optional; defaults keep single-query clients unchanged)
    is_multi: bool = False
    sub_responses: list[dict] = Field(default_factory=list)


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
    return generate_and_execute_with_tools(question, schema, references)


def _is_safe_reference(ex: dict) -> bool:
    """
    Return True if a Pinecone reference row has SQL that passes the same
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


def _build_result_summary(results: list[dict]) -> str | None:
    """Build summary for single-row multi-column (tabular case). Not used for single-value."""
    if not results or len(results) != 1:
        return None
    row = results[0]
    if not row or len(row) == 1:
        return None  # Single value -> use result_sentence instead
    parts = []
    for key, val in row.items():
        s = _format_single_value(val)
        label = key.replace("SUM(", "").replace(")", "").replace("(", " ").strip() or key
        parts.append(f"{label}: {s}")
    return " · ".join(parts)


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


def _process_sub_query_sync(sub_question: str, i: int, total_queries: int, query_id: str, schema: str) -> dict:
    print(f"[Multi-Query] [{query_id}] Processing sub-query {i + 1}/{total_queries}: {sub_question}")

    if is_dangerous_input(sub_question):
        print(f"[Multi-Query] [{query_id}] Sub-query {i + 1} BLOCKED — dangerous input")
        return {
            "question": sub_question, "sql": "", "explanation": "Only read-only queries are allowed. Data modification is not permitted.",
            "results": [], "row_count": 0, "result_sentence": "", "cache_references": [], "status": "error"
        }

    try:
        similar = find_similar_queries(sub_question, top_k=REFERENCE_TOP_K)
        filtered = [ex for ex in similar if _is_safe_reference(ex)]

        tool_result = _run_sql_agent(
            sub_question,
            schema,
            filtered or None,
            thread_id=f"{query_id}-sub-{i}",
        )

        if tool_result["status"] == "not_related":
            print(f"[Multi-Query] [{query_id}] Sub-query {i + 1} — NOT_RELATED")
            return {
                "question": sub_question,
                "sql": "",
                "explanation": tool_result["explanation"],
                "results": [],
                "row_count": 0,
                "result_sentence": "",
                "cache_references": filtered,
                "status": "error",
            }

        if tool_result["status"] in ("db_error", "sql_error"):
            print(f"[Multi-Query] [{query_id}] Sub-query {i + 1} failed: {tool_result['status']}")
            return {
                "question": sub_question,
                "sql": "",
                "explanation": tool_result["explanation"],
                "results": [],
                "row_count": 0,
                "result_sentence": "",
                "cache_references": filtered,
                "status": "error",
            }

        sub_result = tool_result["results"]
        sub_safe_sql = tool_result["sql_query"]
        sub_explanation = tool_result["explanation"]
        sub_row_count = len(sub_result)

        if sub_result:
            if loop:
                loop.call_soon_threadsafe(
                    lambda: loop.run_in_executor(None, store_query, sub_question, sub_safe_sql)
                )
                print(f"[Multi-Query] [{query_id}] Sub-query {i + 1} scheduled for background storage")
            else:
                # Fallback if loop is missing
                store_query(sub_question, sub_safe_sql)

        sub_sentence = _build_result_sentence(sub_result, None)

        sub_narrative = _build_results_narrative(sub_result)
        sub_explanation = _merge_explanation_with_narrative(sub_explanation, sub_narrative)

        print(f"[Multi-Query] [{query_id}] Sub-query {i + 1} SUCCESS — {sub_row_count} rows returned")
        return {
            "question": sub_question, "sql": sub_safe_sql, "explanation": sub_explanation,
            "results": sub_result, "row_count": sub_row_count, "result_sentence": sub_sentence or "",
            "cache_references": filtered, "status": "success"
        }

    except Exception as e:
        print(f"[Multi-Query] [{query_id}] Sub-query {i + 1} unexpected error: {e}")
        return {
            "question": sub_question, "sql": "", "explanation": "An unexpected error occurred. Please try rephrasing.",
            "results": [], "row_count": 0, "result_sentence": "", "cache_references": [], "status": "error"
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

    pref = (body.preference or "AUTO").upper()

    if pref == "SINGLE":
        # Decision already made — skip LLM analysis entirely.
        analysis = {"type": "SINGLE", "queries": [body.question]}
    elif pref == "MULTI":
        analysis = analyze_query(body.question, schema, pref)
    elif config.SKIP_MULTI_QUERY_LLM:
        analysis = {"type": "SINGLE", "queries": [body.question]}
    else:
        # AUTO with multi-indicators OR explicit MULTI pref — run LLM analysis.
        analysis, similar_examples_raw = await asyncio.gather(
            loop.run_in_executor(None, analyze_query, body.question, schema, pref),
            loop.run_in_executor(None, find_similar_queries, body.question, REFERENCE_TOP_K),
        )



    # ── SINGLE question path — identical behavior to the original pipeline ───────
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

        # Semantic cache: Pinecone similarity for reference examples in the prompt.
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

        # Tool calling — LLM generates SQL and executes via tool in one loop
        tool_result = generate_and_execute_with_tools(
            question=body.question,
            schema=schema,
            references=filtered_examples or None,
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
                explanation="Sorry, could not generate a valid query. Please rephrasing.",
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

        # Fire-and-forget: store in Pinecone after response — don't block the user.
        # store_query does OpenAI embedding + Pinecone upsert (~5-8s) — not worth waiting for.
        loop.run_in_executor(None, store_query, body.question, safe_sql)
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
            result_summary=_build_result_summary(result),
            cache_references=filtered_examples or None,
            conversation_id=conversation_id,
        )

    # ── MULTI question path — run each sub-question through a slim pipeline ───────
    elif analysis["type"] == "MULTI":
        query_id = str(uuid.uuid4())
        print(f"[Multi-Query] START query_id={query_id}")
        queries = analysis['queries']
        print(f"[Multi-Query] Sub-queries: {queries}")

        loop = asyncio.get_running_loop()
        tasks = [
            loop.run_in_executor(None, _process_sub_query_sync, sub_question, i, len(queries), query_id, schema, loop)
            for i, sub_question in enumerate(queries)
        ]
        sub_responses = await asyncio.gather(*tasks)

        success_count = sum(1 for r in sub_responses if r["status"] == "success")
        print(
            f"[Multi-Query] DONE query_id={query_id} | "
            f"{success_count}/{len(sub_responses)} succeeded"
        )

        return QueryResponse(
            question=body.question,
            sql="",
            results=[],
            explanation=f"{success_count} of {len(sub_responses)} queries completed successfully.",
            row_count=0,
            conversation_id=conversation_id,
            is_multi=True,
            sub_responses=sub_responses,
        )

    # Should not reach — analyzer always returns SINGLE or MULTI
    return QueryResponse(
        question=body.question,
        sql="",
        results=[],
        explanation="Hmm, something went wrong analyzing your question. Please try again.",
        row_count=0,
        conversation_id=conversation_id,
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

    return await _execute_nl_query(body, conversation_id)