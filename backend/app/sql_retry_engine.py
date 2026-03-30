"""
sql_retry_engine.py
-------------------
Self-healing SQL execution engine with retry logic.

Behavior:
- Validate SQL before execution.
- Retry up to MAX_SQL_RETRIES when SQL is fixable.
- Stop immediately for database connectivity failures.
"""

from __future__ import annotations

from app import config
from app.database import execute_query
from app.query_validator import QueryValidationError, validate_sql
from app.tools.fix_sql_tool import fix_sql_query

# Common keywords that indicate database connectivity/availability problems.
DB_ERROR_KEYWORDS = [
    "connection",
    "timeout",
    "can't connect",
    "refused",
    "network",
    "too many connections",
    "lost connection",
    "server has gone away",
]


def classify_error(error_message: str) -> str:
    """
    Classify an error message into DB-level vs SQL-level failure.

    Returns:
        "DB_ERROR"  -> infra/connection problems; do not retry with LLM.
        "SQL_ERROR" -> query-level problems; can attempt repair and retry.
    """
    msg = (error_message or "").lower()
    if any(keyword in msg for keyword in DB_ERROR_KEYWORDS):
        return "DB_ERROR"
    return "SQL_ERROR"


def execute_with_retry(
    question: str,
    initial_sql: str,
    schema: str,
    max_retries: int | None = None,
) -> dict:
    """
    Execute SQL with self-healing retries.

    Flow:
    1) Validate SQL using the existing safety validator.
    2) Execute query.
    3) If SQL/validation fails, ask LLM to fix and retry (max attempts).
    4) If DB connection-like error occurs, stop immediately.

    Args:
        max_retries: Optional cap on repair attempts; defaults to config.MAX_SQL_RETRIES.

    Returns one of these shapes:
        {"type": "SUCCESS", "results": [...], "sql": "..."}
        {"type": "DB_ERROR", "message": "..."}
        {"type": "SQL_ERROR", "message": "..."}
    """
    # Use parameter when provided; otherwise fall back to global default.
    if max_retries is None:
        max_retries = config.MAX_SQL_RETRIES

    retry_count = 0
    current_sql = initial_sql
    last_error = None

    while retry_count < max_retries:
        # Step 1: Validate SQL using existing guardrails (SELECT-only etc.).
        try:
            current_sql = validate_sql(current_sql)
        except QueryValidationError as e:
            error_msg = str(e)
            print(f"[Retry {retry_count}] Validator failed: {error_msg}")

            # Break if model keeps producing the same failure signal.
            if error_msg == last_error:
                break

            # Ask LLM to fix SQL; stop if nothing changed.
            fixed = fix_sql_query(question, current_sql, error_msg, schema)
            if fixed == current_sql:
                break

            current_sql = fixed
            last_error = error_msg
            retry_count += 1
            continue

        # Step 2: Execute SQL against the database.
        result = execute_query(current_sql)
        print(f"[Retry {retry_count}] SQL: {current_sql}")

        # Step 3: Success path (empty list is still a successful execution).
        if isinstance(result, list):
            return {"type": "SUCCESS", "results": result, "sql": current_sql}

        # Step 4: Error path returned from execute_query.
        if isinstance(result, dict) and "error" in result:
            error_msg = str(result["error"])
            print(f"[Error] {error_msg}")

            error_type = classify_error(error_msg)
            print(f"[Type] {error_type}")

            # DB errors should not trigger LLM retries.
            if error_type == "DB_ERROR":
                return {
                    "type": "DB_ERROR",
                    "message": "Database is currently unavailable. Please try again later.",
                }

            # SQL error: stop if repeated, otherwise try one repair iteration.
            if error_msg == last_error:
                break

            fixed = fix_sql_query(question, current_sql, error_msg, schema)
            if fixed == current_sql:
                break

            current_sql = fixed
            last_error = error_msg
            retry_count += 1

    # Exhausted retries or became stuck with repeated identical failures.
    return {
        "type": "SQL_ERROR",
        "message": "Sorry, I could not generate a valid query after multiple attempts. Please rephrase your question.",
    }

