"""
sql_tools.py
------------
LangChain tool for SQL validation and execution.
This is the ONLY tool the LLM can call.
LLM generates SQL and calls this tool.
Tool validates + executes.
If error occurs, LLM sees the error and fixes SQL itself (self-healing).
LLM decides when to call — not the pipeline code.
"""
from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal

from langchain_core.tools import tool
from app.query_validator import validate_sql, QueryValidationError
from app.database import execute_query


# Keywords that indicate database connectivity failure — not SQL mistake
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


# ---------------------------------------------------------------------------
# Local Serializer (avoid circular import)
# ---------------------------------------------------------------------------
def _make_serializable(obj):
    """Convert non-JSON-serializable DB types to JSON-safe types."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()

    if isinstance(obj, Decimal):
        return float(obj)

    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8")
        except:
            return str(obj)

    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [_make_serializable(i) for i in obj]

    return obj


@tool
def run_sql_query(sql: str) -> dict:
    """
    Validate and execute a SQL SELECT query on the MySQL database.

    Use this tool when you have generated a SQL query and want to
    fetch data from the database. This tool will:
      1. Validate the SQL for safety (SELECT only, no dangerous keywords)
      2. Execute the SQL on the database
      3. Return results or detailed error information

    If this tool returns an error with error_type "VALIDATION" or
    "SQL_ERROR", analyze the error message, fix the SQL, and call
    this tool again with the corrected query.

    STOP immediately if error_type is "DB_ERROR" — do not retry.
    """

    print(f"[Tool:run_sql_query] Called with SQL: {str(sql)[:120]}")

    # -----------------------------------------------------------------------
    # Guard 1: Empty SQL
    # -----------------------------------------------------------------------
    if not sql or not str(sql).strip():
        print("[Tool:run_sql_query] Empty SQL received")
        return {
            "error": "Empty SQL query provided.",
            "error_type": "VALIDATION",
            "sql": sql
        }

    # -----------------------------------------------------------------------
    # Step 1: Validate SQL safety
    # -----------------------------------------------------------------------
    try:
        validated_sql = validate_sql(sql)
        print("[Tool:run_sql_query] Validation passed")
    except QueryValidationError as e:
        print(f"[Tool:run_sql_query] Validation failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "error_type": "VALIDATION",
            "sql": sql
        }

    # -----------------------------------------------------------------------
    # Step 2: Execute query (SAFE)
    # -----------------------------------------------------------------------
    try:
        result = execute_query(validated_sql)
        print("[Tool:run_sql_query] Execution done")
    except Exception as e:
        error_msg = str(e)
        print(f"[Tool:run_sql_query] Execution exception: {error_msg}")

        return {
            "success": False,
            "error": error_msg,
            "error_type": "DB_ERROR",
            "sql": validated_sql
        }

    # -----------------------------------------------------------------------
    # Guard 2: Unexpected result type
    # -----------------------------------------------------------------------
    if result is None:
        return {
            "success": False,
            "error": "Database returned no response.",
            "error_type": "DB_ERROR",
            "sql": validated_sql
        }

    # -----------------------------------------------------------------------
    # Step 3: Handle execution errors
    # -----------------------------------------------------------------------
    if isinstance(result, dict) and "error" in result:
        error_msg = str(result["error"])
        error_type = "DB_ERROR" if any(
            k in error_msg.lower() for k in DB_ERROR_KEYWORDS
        ) else "SQL_ERROR"

        print(f"[Tool:run_sql_query] Execution error ({error_type}): {error_msg}")

        return {
            "success": False,
            "error": error_msg,
            "error_type": error_type,
            "sql": validated_sql
        }

    # -----------------------------------------------------------------------
    # Step 4: Serialize results safely
    # -----------------------------------------------------------------------
    safe_results = _make_serializable(result)

    # Guard: Ensure list format
    if not isinstance(safe_results, list):
        safe_results = [safe_results]

    print(f"[Tool:run_sql_query] Success — {len(safe_results)} rows returned")

    return {
        "success": True,
        "results": safe_results,
        "row_count": len(safe_results),
        "sql": validated_sql
    }

@tool
def render_pie_chart(label_column: str, value_column: str) -> dict:
    """
    Call this tool in PARALLEL with run_sql_query when the user requests a pie chart visualization or the data inherently represents a distribution/pie chart.
    Specify exactly which column should be the label/category, and which column should be the numerical value.
    Example: render_pie_chart(label_column="status", value_column="total_count")
    """
    return {
        "success": True,
        "is_pie_chart": True,
        "label_column": label_column,
        "value_column": value_column
    }
