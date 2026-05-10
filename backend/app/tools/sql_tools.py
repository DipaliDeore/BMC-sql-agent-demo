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
import re

# pyrefly: ignore [missing-import]
from langchain_core.tools import tool
from app.query_validator import validate_sql, QueryValidationError
from app.database import execute_query, select_sql_with_row_limit


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


def _normalize_mysql_sql(sql: str) -> str:
    """
    Normalize common non-MySQL date expressions produced by LLMs.
    Keeps behavior targeted to avoid changing valid MySQL SQL.
    """
    if not sql:
        return sql

    # SQLite style: strftime('%Y-%m', order_date) -> DATE_FORMAT(order_date, '%Y-%m')
    normalized = re.sub(
        r"strftime\(\s*'(%[^']+)'\s*,\s*([^)]+?)\s*\)",
        r"DATE_FORMAT(\2, '\1')",
        sql,
        flags=re.IGNORECASE,
    )

    lower_sql = normalized.lower()
    has_order_items = "from order_items" in lower_sql
    has_orders_join = " join orders " in lower_sql
    references_order_date = "order_date" in lower_sql

    # Common LLM mistake: filtering order_items by order_date without joining orders.
    if has_order_items and references_order_date and not has_orders_join:
        normalized = re.sub(
            r"\bFROM\s+order_items\b(?:\s+(\w+))?",
            "FROM order_items oi JOIN orders o ON oi.order_id = o.order_id",
            normalized,
            count=1,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            r"(?<![\w.])order_date(?![\w.])",
            "o.order_date",
            normalized,
            flags=re.IGNORECASE,
        )
    return normalized


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

    normalized_sql = _normalize_mysql_sql(str(sql))
    if normalized_sql != str(sql):
        print("[Tool:run_sql_query] Rewrote SQL to MySQL-compatible date functions")

    # -----------------------------------------------------------------------
    # Step 1: Validate SQL safety
    # -----------------------------------------------------------------------
    try:
        validated_sql = validate_sql(normalized_sql)
        print("[Tool:run_sql_query] Validation passed")
    except QueryValidationError as e:
        print(f"[Tool:run_sql_query] Validation failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "error_type": "VALIDATION",
            "sql": normalized_sql
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
        "sql": select_sql_with_row_limit(validated_sql),
    }


# ---------------------------------------------------------------------------
# chart_config contract (API + SSE + chat UI)
# ---------------------------------------------------------------------------
# Tool ``render_chart`` returns a marker payload (no rows). After
# ``run_sql_query``, the executor matches markers to result sets by checking
# that x_column and y_column exist on the first result row, then attaches:
#
#   {
#     "chart_type": "pie" | "bar" | "line",
#     "x_column": str,   # category / time / ordered dimension
#     "y_column": str,   # primary numeric measure
#     "y_column_2": str | None,  # optional second series (line/bar only), e.g. failed vs successful counts
#     "is_pie_chart": bool,  # True iff chart_type == "pie" (backward compat)
#   }
#
# Legacy pie-only payloads used label_column + value_column + is_pie_chart;
# the executor normalizes those to the shape above.


_VALID_CHART_TYPES = frozenset({"pie", "bar", "line"})


@tool
def render_chart(chart_type: str, x_column: str, y_column: str, y_column_2: str = "") -> dict:
    """
    Declare how to visualize a prior ``run_sql_query`` result. Call ONLY after
    you have seen the SQL rows, using exact column names from that result.

    - chart_type ``pie``: part-to-whole / distribution (categories + shares).
    - chart_type ``bar``: rankings or comparisons across discrete categories.
    - chart_type ``line``: trends or time-ordered series (x_column is time/order).

    For ``line`` or ``bar`` when comparing two metrics over the same x (e.g. successful
    vs failed payments by day), use optional ``y_column_2`` for the second numeric column.
    Prefer reshaping SQL to one row per x with two count columns, then call
    ``render_chart(..., y_column="completed_count", y_column_2="failed_count")``.

    Two-step flow (sequential, not parallel with the same SQL you have not run yet):
      1) ``run_sql_query``
      2) ``render_chart`` with the same row shape you received.

    Example: render_chart(chart_type="bar", x_column="product_name", y_column="total_sales")
    Example (dual series): render_chart(chart_type="line", x_column="payment_date", y_column="successful_count", y_column_2="failed_count")
    """
    ct = (chart_type or "").strip().lower()
    if ct not in _VALID_CHART_TYPES:
        return {
            "success": False,
            "error": f"Invalid chart_type {chart_type!r}. Use one of: pie, bar, line.",
            "error_type": "VALIDATION",
        }
    xc = (x_column or "").strip()
    yc = (y_column or "").strip()
    if not xc or not yc:
        return {
            "success": False,
            "error": "x_column and y_column must be non-empty.",
            "error_type": "VALIDATION",
        }
    y2 = (y_column_2 or "").strip() or None
    if y2 and ct == "pie":
        return {
            "success": False,
            "error": "y_column_2 is only supported for chart_type bar or line.",
            "error_type": "VALIDATION",
        }
    if y2 and y2 == yc:
        return {
            "success": False,
            "error": "y_column_2 must differ from y_column.",
            "error_type": "VALIDATION",
        }

    out: dict = {
        "success": True,
        "chart_type": ct,
        "x_column": xc,
        "y_column": yc,
        "is_pie_chart": ct == "pie",
        "label_column": xc,
        "value_column": yc,
    }
    if y2:
        out["y_column_2"] = y2
    return out

