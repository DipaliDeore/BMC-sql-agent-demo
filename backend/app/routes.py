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

    # Step 1: Get the database schema to give the AI context
    schema = get_database_schema()

    # Step 2: Call Gemini to generate SQL + a plain-English explanation
    try:
        ai_result = generate_sql_and_explanation(body.question, schema)
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

    # Step 5: Calculate row count and return the full response
    row_count = len(result)

    return QueryResponse(
        question=body.question,
        sql=safe_sql,
        results=result,
        explanation=explanation,
        row_count=row_count,
    )