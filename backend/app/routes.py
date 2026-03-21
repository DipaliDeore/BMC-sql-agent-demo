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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import execute_query, get_database_schema
from app.sql_generator import generate_sql_and_explanation, is_dangerous_input
from app.query_validator import validate_sql, QueryValidationError
from app.search import find_similar_queries
from app.store import store_query


# ── Create API Router ─────────────────────────────────────────────────────────
# All routes defined here will automatically get the /api prefix.
# Example: "/query" becomes "/api/query"
router = APIRouter(prefix="/api", tags=["SQL Agent"])


# ── Request / Response Models ─────────────────────────────────────────────────

class QueryRequest(BaseModel):
    """Request body for the POST /api/query endpoint."""
    question: str  # The user's natural language question


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
            detail=f"Database connection failed: {result['error']}"
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

    # Reject empty questions
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    # ── Security Check: Detect dangerous input BEFORE calling Gemini ─────────────
    # This pre-check runs before the AI model is called, so dangerous queries
    # are blocked immediately with a security warning instead of being processed.
    if is_dangerous_input(body.question):
        return QueryResponse(
            question=body.question,
            sql="",
            results=[],
            explanation="This operation is not permitted. Only read-only queries are allowed. Data modification operations such as DELETE, UPDATE, INSERT, and DROP are not supported.",
            row_count=0
        )

    # ── Semantic cache: retrieve top-3 similar references (optional) ────────────
    # Instead of directly reusing the cached SQL, we provide (question, SQL) pairs
    # as reference examples to the LLM so it can generate the correct SQL for the
    # current question. Cache is optional; if Pinecone/OpenAI are unavailable,
    # `find_similar_queries` returns an empty list.
    similar_examples = find_similar_queries(body.question, top_k=3)

    # Filter out any unsafe cached SQL so the prompt only contains safe references.
    filtered_examples: list[dict] = []
    for ex in similar_examples:
        try:
            candidate_sql = (ex.get("sql") or "").strip()
            if candidate_sql:
                validate_sql(candidate_sql)
                filtered_examples.append(ex)
        except QueryValidationError:
            continue

    # ── Generate SQL via AI (guided by references when available) ─────────────
    # Step 1: Get the database schema to give the AI context
    schema = get_database_schema()

    # Step 2: Call Gemini to generate SQL + a plain-English explanation
    try:
        ai_result = generate_sql_and_explanation(
            body.question, schema, references=filtered_examples or None
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI generation failed: {e}")

    # Extract both fields from the AI response
    sql_query = ai_result["sql_query"]
    explanation = ai_result["explanation"]

    # ── Edge Case: Question is not related to the database ──────────────
    # If the AI determined the question has no relation to the DB schema,
    # return the explanation without any SQL or results.
    if sql_query == "NOT_RELATED":
        return QueryResponse(
            question=body.question,
            sql="",
            results=[],
            explanation=explanation,
            row_count=0,
        )

    # ── Edge Case: Gemini returned an empty SQL query ────────────────────
    # If the AI generated an empty or whitespace-only query, return safely
    # with empty results instead of crashing.
    if not sql_query or not sql_query.strip():
        return QueryResponse(
            question=body.question,
            sql="",
            results=[],
            explanation=explanation,
            row_count=0,
        )

    # Step 3: Validate the generated SQL (blocks dangerous queries)
    try:
        safe_sql = validate_sql(sql_query)
    except QueryValidationError:
        # Return a friendly message instead of a 422 error
        return QueryResponse(
            question=body.question,
            sql="",
            results=[],
            explanation="Only read-only queries are allowed. Data modification operations are not permitted.",
            row_count=0,
        )

    # Step 4: Execute the validated SQL against the database
    result = execute_query(safe_sql)

    # execute_query returns {"error": "..."} on failure
    # Return a friendly message instead of a 500 error
    if isinstance(result, dict) and "error" in result:
        return QueryResponse(
            question=body.question,
            sql=safe_sql,
            results=[],
            explanation="There was an error executing the query. Please try rephrasing your question.",
            row_count=0,
        )

    # ── Edge Case: Query returned no rows ────────────────────────────────
    # If the query ran successfully but returned no rows,
    # set a friendly explanation message.
    if not result:
        return QueryResponse(
            question=body.question,
            sql=safe_sql,
            results=[],
            explanation="No records found for your query.",
            row_count=0,
        )

    # Step 5: Store this (question, sql) pair in Pinecone for future semantic cache hits
    # Only store after successful execution so the cache always contains valid pairs.
    store_query(body.question, safe_sql)

    # Step 6: Build result_sentence (use AI answer_template for single value if provided)
    # Step 5: Store this (question, sql) pair in Pinecone for future semantic cache hits
    # Only store after successful execution so the cache always contains valid pairs.
    store_query(body.question, safe_sql)

    # Step 6: Build result_sentence (use AI answer_template for single value if provided)
    row_count = len(result)
    answer_template = ai_result.get("answer_template")
    answer_template = ai_result.get("answer_template")

    return QueryResponse(
        question=body.question,
        sql=safe_sql,
        results=result,
        explanation=explanation,
        row_count=row_count,
        result_sentence=_build_result_sentence(result, answer_template),
        result_summary=_build_result_summary(result),
        cache_references=filtered_examples or None,
    )