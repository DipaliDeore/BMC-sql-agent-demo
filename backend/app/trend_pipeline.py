"""
Lightweight pipeline for time-series / trend questions (one LLM call + SQL).
"""

from __future__ import annotations

from typing import Any

# pyrefly: ignore [missing-import]
from langchain_core.messages import HumanMessage

from app import config
from app.llm_errors import invoke_with_retry, rate_limited
from app.query_validator import QueryValidationError, validate_sql
from app.serialization import make_json_serializable
from app.response_formatting import format_single_value
from app.pipeline_sql_utils import broaden_time_series_sql, time_series_status_rules
from app.strategic_pipeline import (
    _execute_safe_sql,
    _extract_json_object,
    _get_strategic_llm,
)

TREND_RESPONSE_KIND = "trend_series"


def _time_dimension_keys(row: dict) -> list[str]:
    if not isinstance(row, dict):
        return []
    out: list[str] = []
    for key in row:
        kl = (key or "").lower()
        if any(t in kl for t in ("date", "month", "day", "week", "year", "period", "time")):
            out.append(key)
    return out


def _metric_keys(row: dict) -> list[str]:
    if not isinstance(row, dict):
        return []
    time_keys = set(_time_dimension_keys(row))
    out: list[str] = []
    for key, val in row.items():
        if key in time_keys:
            continue
        try:
            float(val)
            out.append(key)
        except (TypeError, ValueError):
            if isinstance(val, (int, float)):
                out.append(key)
    return out


def should_use_trend_pipeline(question: str, plan: dict[str, Any]) -> bool:
    from app.strategic_pipeline import should_use_strategic_pipeline

    if plan.get("strategy") in ("strategic_mode", "deterministic_sql"):
        return False
    if should_use_strategic_pipeline(question, plan):
        return False
    ql = (question or "").lower()
    from app.forecast_pipeline import _is_forecast_question

    if _is_forecast_question(ql) or "forecast" in (plan.get("intents") or []):
        return False
    if plan.get("chart_hint") == "line":
        return True
    if "trend" not in ql:
        return False
    return any(
        p in ql
        for p in (
            "over time",
            "by month",
            "by day",
            "by week",
            "daily",
            "monthly",
            "weekly",
            "time series",
        )
    )


def _plan_trend_sql(question: str, schema: str, references_text: str) -> str | None:
    llm = _get_strategic_llm()
    prompt = f"""Write ONE MySQL/TiDB SELECT for a time-series / trend question.

Return ONLY JSON: {{"queries": ["SELECT ..."]}}

Rules:
- Exactly one query
- GROUP BY a time bucket (month or day) using DATE_FORMAT / YEAR / MONTH on a date column
- Include one numeric aggregate (SUM, COUNT, or AVG) for the metric in the question
- Return ALL periods that exist in the data (no WHERE filter on a single month unless the user asked for one)
- ORDER BY the time column ascending
- Use ONLY tables/columns from the schema
- SELECT only; LIMIT 100
{time_series_status_rules()}

Question: {question.strip()}

Schema:
{schema}

Hints:
{references_text or "None"}
"""
    response = invoke_with_retry(lambda: llm.invoke([HumanMessage(content=prompt)]))
    content = response.content
    if isinstance(content, list):
        content = " ".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    payload = _extract_json_object(str(content))
    if not payload:
        return None
    raw = payload.get("queries") or payload.get("sql") or []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        return None
    sql = str(raw[0]).strip().rstrip(";")
    if not sql:
        return None
    try:
        validate_sql(sql)
    except QueryValidationError:
        return None
    return sql


def _trend_explanation(question: str, rows: list[dict]) -> str:
    if not rows:
        return (
            "No refund amounts were found for a time breakdown. "
            "Check that returns and refunds are recorded in the database."
        )

    first = rows[0] if isinstance(rows[0], dict) else {}
    time_keys = _time_dimension_keys(first)
    metric_keys = _metric_keys(first)
    time_key = time_keys[0] if time_keys else list(first.keys())[0] if first else ""
    metric_key = metric_keys[0] if metric_keys else ""

    if len(rows) == 1 and time_key and metric_key:
        period = format_single_value(first.get(time_key))
        amount = format_single_value(first.get(metric_key))
        metric_label = metric_key.replace("_", " ")
        return (
            f"Your data only includes one time period ({period}), with {metric_label} of {amount}. "
            "A trend over time needs at least two periods (for example, two or more months). "
            "The table below shows this single period; no trend line is shown."
        )

    if len(rows) >= 2 and metric_key:
        try:
            vals = [float(r.get(metric_key) or 0) for r in rows if isinstance(r, dict)]
            periods = [
                format_single_value(r.get(time_key)) for r in rows if isinstance(r, dict)
            ]
            first_val, last_val = vals[0], vals[-1]
            direction = (
                "increased"
                if last_val > first_val
                else "decreased"
                if last_val < first_val
                else "stayed flat"
            )
            metric_label = metric_key.replace("_", " ")
            return (
                f"Refund amounts over {len(rows)} periods ({periods[0]} through {periods[-1]}): "
                f"{metric_label} {direction} from {first_val:,.2f} to {last_val:,.2f}. "
                "See the line chart and table for the full breakdown."
            )
        except (TypeError, ValueError):
            pass

    return (
        f"Here are refund amounts across {len(rows)} period(s). "
        "See the chart and table below."
    )


def execute_trend_pipeline(
    question: str,
    schema: str,
    references_text: str = "",
) -> dict[str, Any] | None:
    try:
        sql = _plan_trend_sql(question, schema, references_text)
    except Exception as exc:
        if rate_limited(exc):
            return {
                "sql_query": "",
                "explanation": (
                    "The AI service quota has been reached. Please wait a few minutes "
                    "or try again later."
                ),
                "results": [],
                "row_count": 0,
                "status": "rate_limited",
            }
        print(f"[TrendPipeline] SQL planning failed: {exc}")
        return None

    if not sql:
        return None

    data = _execute_safe_sql(sql)
    if not data.get("success"):
        return None

    rows = make_json_serializable(data.get("results") or [])
    if not isinstance(rows, list):
        rows = [rows]

    if not rows:
        broadened = broaden_time_series_sql(sql)
        if broadened:
            print(f"[TrendPipeline] Retrying without status filters: {broadened[:120]}")
            data2 = _execute_safe_sql(broadened)
            if data2.get("success") and data2.get("results"):
                data = data2
                sql = broadened
                rows = make_json_serializable(data.get("results") or [])
                if not isinstance(rows, list):
                    rows = [rows]

    if not rows:
        return {
            "sql_query": data.get("sql") or sql,
            "explanation": _trend_explanation(question, []),
            "results": [],
            "row_count": 0,
            "status": "success",
            "is_multi": False,
        }

    return {
        "sql_query": data.get("sql") or sql,
        "explanation": _trend_explanation(question, rows),
        "results": rows,
        "row_count": len(rows),
        "status": "success",
        "is_multi": False,
        "response_kind": TREND_RESPONSE_KIND,
    }
