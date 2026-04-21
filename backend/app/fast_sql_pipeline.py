"""
fast_sql_pipeline.py
--------------------
One Gemini call to produce SQL (JSON) + validate + execute, with at most one
repair pass on validation or execution errors. Avoids the ReAct tool loop so
typical requests finish in a few seconds instead of many round-trips.

LangSmith notes
~~~~~~~~~~~~~~~
* **No LLM ``tool_calls`` here:** the model returns SQL inside JSON text. It does
  not use Gemini/LangChain function-calling, so you will not see provider-native
  "tool call" blocks for SQL generation—only normal LLM completion.
* **SQL execution** is plain Python (``execute_query``), not ``llm.bind_tools``.
  We wrap it in ``@traceable(..., run_type="tool")`` named ``run_sql_query`` so
  LangSmith still shows a **tool-shaped** child run (SQL in → rows/error out).
* The **table** view in LangSmith is just the UI formatting for structured
  **inputs/outputs** (key/value or JSON), not "only a database table."
* To see **LangGraph ``tools`` nodes** and real bound-tool traces, set
  ``USE_FAST_SQL_PIPELINE=false`` (slower, ReAct loop).
"""

from __future__ import annotations

from collections.abc import Callable

from langsmith import traceable

from app.serialization import make_json_serializable
from app.database import execute_query, iter_query_rows
from app.query_validator import QueryValidationError, validate_sql
from app.sql_generator import generate_sql_and_explanation
from app.tools.fix_sql_tool import fix_sql_query
from app.tools.sql_tools import DB_ERROR_KEYWORDS


@traceable(name="run_sql_query", run_type="tool")
def _traced_execute_query(sql: str):
    """
    Same as ``execute_query`` but emitted to LangSmith as a tool run so the trace
    shows an explicit SQL execution step under ``sql_demo_query``.
    """
    return execute_query(sql)


@traceable(name="run_sql_query_row_stream", run_type="tool")
def _traced_execute_query_streaming(sql: str, on_row: Callable[[dict], None]) -> list | dict:
    """
    Like ``_traced_execute_query`` but reads rows via ``iter_query_rows`` (fetchmany)
    and invokes ``on_row`` for each row before returning the full list (or error dict).
    """
    rows: list[dict] = []
    try:
        for row in iter_query_rows(sql, batch_size=200):
            rows.append(row)
            on_row(row)
        return rows
    except Exception as e:
        return {"error": str(e)}


def _rate_limited(exc: BaseException) -> bool:
    s = str(exc).lower()
    return "429" in s or "resource_exhausted" in s or "quota" in s


def _is_db_error(message: str) -> bool:
    low = message.lower()
    return any(k in low for k in DB_ERROR_KEYWORDS)


def run_fast_sql_pipeline_after_gen(
    gen: dict,
    question: str,
    schema: str,
    *,
    on_row: Callable[[dict], None] | None = None,
) -> dict:
    """
    Validate + execute (+ optional repair) given an already-parsed generator dict.

    When ``on_row`` is set, successful SELECTs stream rows through it using chunked DB reads.
    """
    sql_raw = (gen.get("sql_query") or "").strip()
    explanation = (gen.get("explanation") or "").strip()
    answer_template = gen.get("answer_template")

    if sql_raw == "NOT_RELATED":
        return {
            "sql_query": "",
            "explanation": explanation or "I'm focused on this app's data — try a question about customers, products, or orders.",
            "results": [],
            "row_count": 0,
            "status": "not_related",
            "answer_template": answer_template,
        }

    validated: str | None = None
    try:
        validated = validate_sql(sql_raw)
    except QueryValidationError as ve:
        fixed = fix_sql_query(question, sql_raw, str(ve), schema)
        if not fixed or fixed.strip() == sql_raw.strip():
            return {
                "sql_query": "",
                "explanation": "Sorry, could not generate a valid query. Please try rephrasing.",
                "results": [],
                "row_count": 0,
                "status": "sql_error",
                "answer_template": None,
            }
        try:
            validated = validate_sql(fixed)
        except QueryValidationError:
            return {
                "sql_query": "",
                "explanation": "Sorry, could not generate a valid query. Please try rephrasing.",
                "results": [],
                "row_count": 0,
                "status": "sql_error",
                "answer_template": None,
            }

    assert validated is not None
    if on_row is None:
        result = _traced_execute_query(validated)
    else:
        result = _traced_execute_query_streaming(validated, on_row)

    if not isinstance(result, dict) or "error" not in result:
        rows = make_json_serializable(result)
        if not isinstance(rows, list):
            rows = [rows]
        return {
            "sql_query": validated,
            "explanation": explanation or "Query executed successfully.",
            "results": rows,
            "row_count": len(rows),
            "status": "success",
            "answer_template": answer_template,
        }

    err = str(result["error"])
    if _is_db_error(err):
        return {
            "sql_query": "",
            "explanation": "Database is currently unavailable. Please try again later.",
            "results": [],
            "row_count": 0,
            "status": "db_error",
            "answer_template": None,
        }

    fixed2 = fix_sql_query(question, validated, err, schema)
    if not fixed2 or fixed2.strip() == validated.strip():
        return {
            "sql_query": "",
            "explanation": explanation or "Sorry, could not run the query against the database.",
            "results": [],
            "row_count": 0,
            "status": "sql_error",
            "answer_template": None,
        }

    try:
        v2 = validate_sql(fixed2)
    except QueryValidationError:
        return {
            "sql_query": "",
            "explanation": "Sorry, could not generate a valid query. Please try rephrasing.",
            "results": [],
            "row_count": 0,
            "status": "sql_error",
            "answer_template": None,
        }

    if on_row is None:
        result2 = _traced_execute_query(v2)
    else:
        result2 = _traced_execute_query_streaming(v2, on_row)

    if isinstance(result2, dict) and "error" in result2:
        err2 = str(result2["error"])
        if _is_db_error(err2):
            return {
                "sql_query": "",
                "explanation": "Database is currently unavailable. Please try again later.",
                "results": [],
                "row_count": 0,
                "status": "db_error",
                "answer_template": None,
            }
        return {
            "sql_query": "",
            "explanation": explanation or "Sorry, could not run the query against the database.",
            "results": [],
            "row_count": 0,
            "status": "sql_error",
            "answer_template": None,
        }

    rows = make_json_serializable(result2)
    if not isinstance(rows, list):
        rows = [rows]
    return {
        "sql_query": v2,
        "explanation": explanation or "Query executed successfully.",
        "results": rows,
        "row_count": len(rows),
        "status": "success",
        "answer_template": answer_template,
    }


def run_fast_sql_pipeline(
    question: str,
    schema: str,
    references: list | None,
    *,
    thread_id: str | None = None,
) -> dict:
    """
    Same return shape as ``generate_and_execute_with_tools``, plus optional
    ``answer_template`` when present in the generator JSON.
    """
    try:
        gen = generate_sql_and_explanation(
            question,
            schema,
            references,
            thread_id=thread_id,
        )
    except Exception as e:
        if _rate_limited(e):
            return {
                "sql_query": "",
                "explanation": "The AI service is temporarily rate-limited. Please try again shortly.",
                "results": [],
                "row_count": 0,
                "status": "rate_limited",
            }
        raise

    return run_fast_sql_pipeline_after_gen(gen, question, schema, on_row=None)
