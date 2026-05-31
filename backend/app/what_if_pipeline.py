"""
what_if_pipeline.py — Hypothetical / scenario analysis via read-only simulated SQL.
"""

from __future__ import annotations

import re
from typing import Any

# pyrefly: ignore [missing-import]
from langchain_core.messages import HumanMessage

from app.llm_errors import invoke_with_retry, rate_limited
from app.query_validator import QueryValidationError, validate_sql
from app.response_formatting import format_single_value
from app.serialization import make_json_serializable
from app.strategic_pipeline import (
    _execute_safe_sql,
    _extract_json_object,
    _get_strategic_llm,
)
from app.what_if_heuristics import build_heuristic_plan

WHAT_IF_RESPONSE_KIND = "what_if_analysis"


def _is_what_if_question(ql: str) -> bool:
    if re.search(r"\bwhat\s+if\b", ql):
        return True
    if re.search(r"\bwhat would happen if\b", ql):
        return True
    if re.search(r"\b(suppose|hypothetically|hypothetical|simulate|simulation|scenario)\b", ql):
        return True
    if re.search(
        r"\b(increase|decrease|drop|raise|lower|reduce|grow|decline|improve|convert)(d|s|ing|ment)?\s+by\s+\d+(\.\d+)?\s*%",
        ql,
    ):
        return True
    if re.search(r"\b(\d+(?:\.\d+)?)\s*%\s*(discount|off)\b", ql):
        return True
    if re.search(r"\bif\s+.+\s+(increased|decreased|doubled|halved)\b", ql):
        return True
    if re.search(r"\b(double|doubled|triple|tripled|halve|halved|eliminate|stop selling)\b", ql):
        return True
    if re.search(r"\btop\s+\d+\s+products?\b", ql):
        return True
    if any(
        p in ql
        for p in (
            "promote",
            "slow-moving",
            "slow moving",
            "high-selling",
            "high selling",
            "best seller",
            "repeat customer",
            "one-time buyer",
            "one time buyer",
            "high-value customer",
            "refund",
            "return",
            "delivery",
            "competitor",
        )
    ):
        return True
    return False


def should_use_what_if_pipeline(question: str, plan: dict[str, Any]) -> bool:
    from app.strategic_pipeline import should_use_strategic_pipeline
    from app.trend_pipeline import should_use_trend_pipeline

    if plan.get("strategy") in ("strategic_mode", "deterministic_sql"):
        return False
    if plan.get("strategy") == "what_if_mode":
        return True
    ql = (question or "").lower()
    if not _is_what_if_question(ql):
        return False
    if should_use_strategic_pipeline(question, plan) and not re.search(
        r"\b(what\s+if|what would|suppose|simulate|\d+\s*%|double|discount)\b", ql
    ):
        return False
    if should_use_trend_pipeline(question, plan) and "what if" not in ql:
        return False
    return True


def _plan_what_if_sql(
    question: str, schema: str, references_text: str
) -> dict[str, Any] | None:
    llm = _get_strategic_llm()
    prompt = f"""You plan a WHAT-IF / scenario analysis for a MySQL/TiDB database (read-only).

User question: {question.strip()}

Schema:
{schema}

References:
{references_text or "None"}

Return ONLY JSON:
{{
  "queries": ["SELECT ..."],
  "scenario_summary": "short label",
  "baseline_column": "baseline column alias",
  "scenario_column": "scenario column alias"
}}

Rules:
- ONE SELECT, ONE row, baseline + scenario numeric columns (snake_case aliases).
- Simulate ONLY with expressions (multiply, add, CASE). NEVER UPDATE/INSERT/DELETE.
- Tables: order_items (price_at_purchase, quantity), orders, customers, refunds, returns, shipping, products, payments.
- Examples:
  * Total sales +10%: SUM(qty*price) and SUM(qty*price)*1.10
  * Top 5 products double: total + top5_sales*(multiplier-1)
  * Stop low performers: total minus bottom-N product sales
  * Repeat customers +20%: scale repeat-customer revenue slice only
  * Refunds -30%: SUM(refund_amount)*0.7
  * Price +5% on all items: SUM(qty*price*1.05)
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
    queries: list[str] = []
    for q in raw[:2]:
        sql = str(q).strip().rstrip(";")
        if not sql:
            continue
        try:
            validate_sql(sql)
        except QueryValidationError:
            return None
        queries.append(sql)
    if not queries:
        return None
    return {
        "queries": queries,
        "scenario_summary": str(payload.get("scenario_summary") or "What-if scenario").strip(),
        "baseline_column": str(payload.get("baseline_column") or "").strip(),
        "scenario_column": str(payload.get("scenario_column") or "").strip(),
    }


def _numeric_columns(row: dict) -> list[str]:
    out: list[str] = []
    for key, val in row.items():
        if val is None:
            continue
        try:
            float(val)
            out.append(key)
        except (TypeError, ValueError):
            if isinstance(val, (int, float)):
                out.append(key)
    return out


def _pick_baseline_scenario_cols(
    row: dict,
    baseline_hint: str,
    scenario_hint: str,
) -> tuple[str, str] | None:
    if not isinstance(row, dict) or len(row) < 2:
        return None
    keys = list(row.keys())
    bl = baseline_hint.lower()
    sc = scenario_hint.lower()
    if bl and sc and bl in {k.lower() for k in keys} and sc in {k.lower() for k in keys}:
        b_key = next(k for k in keys if k.lower() == bl)
        s_key = next(k for k in keys if k.lower() == sc)
        return b_key, s_key
    nums = _numeric_columns(row)
    if len(nums) >= 2:
        baseline_key = nums[0]
        scenario_key = nums[1]
        for k in nums:
            kl = k.lower()
            if "baseline" in kl or "current" in kl or "actual" in kl:
                baseline_key = k
            if "scenario" in kl or "what_if" in kl or "simulated" in kl or "projected" in kl:
                scenario_key = k
        return baseline_key, scenario_key
    return None


def _what_if_explanation(
    question: str,
    row: dict,
    *,
    baseline_key: str,
    scenario_key: str,
    scenario_summary: str,
) -> str:
    try:
        baseline = float(row.get(baseline_key) or 0)
        scenario = float(row.get(scenario_key) or 0)
    except (TypeError, ValueError):
        return (
            f"Scenario analysis ({scenario_summary}): see the table below for baseline vs simulated values."
        )

    delta = scenario - baseline
    pct = (delta / baseline * 100.0) if baseline else 0.0
    b_fmt = format_single_value(baseline)
    s_fmt = format_single_value(scenario)
    d_fmt = format_single_value(abs(delta))
    sign = "+" if delta >= 0 else "-"
    metric = baseline_key.replace("_", " ")

    lines = [
        f"**What-if analysis:** {scenario_summary}",
        "",
        f"- **Current (baseline) {metric}:** {b_fmt}",
        f"- **Simulated scenario:** {s_fmt}",
        f"- **Change:** {sign}{d_fmt} ({pct:+.1f}% vs baseline)",
        "",
        "This is a read-only simulation — no data was changed in the database.",
    ]
    return "\n".join(lines)


def _comparison_table_rows(
    baseline_key: str,
    scenario_key: str,
    row: dict,
    scenario_summary: str,
) -> list[dict[str, Any]]:
    return [
        {
            "scenario": "Current (baseline)",
            "metric": baseline_key.replace("_", " "),
            "value": row.get(baseline_key),
        },
        {
            "scenario": f"What-if ({scenario_summary})",
            "metric": scenario_key.replace("_", " "),
            "value": row.get(scenario_key),
        },
    ]


def _build_result_from_plan(
    question: str,
    plan: dict[str, Any],
) -> dict[str, Any] | None:
    queries = plan["queries"]
    sql_combined = ";\n".join(queries)
    data = _execute_safe_sql(queries[0])
    if not data.get("success"):
        return None

    rows = make_json_serializable(data.get("results") or [])
    if not isinstance(rows, list):
        rows = [rows]
    if not rows or not isinstance(rows[0], dict):
        return {
            "sql_query": data.get("sql") or queries[0],
            "explanation": (
                "I could not compute a what-if comparison from the database. "
                "Try naming the metric (e.g. sales, revenue) and the change (e.g. +10%)."
            ),
            "results": [],
            "row_count": 0,
            "status": "success",
            "is_multi": False,
            "response_kind": WHAT_IF_RESPONSE_KIND,
        }

    row = rows[0]
    pair = _pick_baseline_scenario_cols(
        row,
        plan.get("baseline_column") or "",
        plan.get("scenario_column") or "",
    )
    if not pair:
        return {
            "sql_query": data.get("sql") or queries[0],
            "explanation": (
                "The query ran, but I could not identify baseline vs scenario columns. "
                "See the raw result below."
            ),
            "results": rows,
            "row_count": len(rows),
            "status": "success",
            "is_multi": False,
            "response_kind": WHAT_IF_RESPONSE_KIND,
        }

    baseline_key, scenario_key = pair
    scenario_summary = plan.get("scenario_summary") or "scenario"
    explanation = _what_if_explanation(
        question,
        row,
        baseline_key=baseline_key,
        scenario_key=scenario_key,
        scenario_summary=scenario_summary,
    )
    display_rows = _comparison_table_rows(
        baseline_key, scenario_key, row, scenario_summary
    )

    chart_config: dict[str, Any] | None = {
        "chart_type": "bar",
        "x_column": "scenario",
        "y_column": "value",
        "is_pie_chart": False,
    }

    return {
        "sql_query": data.get("sql") or sql_combined,
        "explanation": explanation,
        "results": display_rows,
        "row_count": len(display_rows),
        "status": "success",
        "is_multi": False,
        "response_kind": WHAT_IF_RESPONSE_KIND,
        "chart_config": chart_config,
        "what_if_meta": {
            "scenario_summary": scenario_summary,
            "baseline_column": baseline_key,
            "scenario_column": scenario_key,
            "raw_result": row,
        },
    }


def execute_what_if_pipeline(
    question: str,
    schema: str,
    references_text: str = "",
) -> dict[str, Any] | None:
    plan = build_heuristic_plan(question, schema)

    if not plan:
        try:
            plan = _plan_what_if_sql(question, schema, references_text)
        except Exception as exc:
            if rate_limited(exc):
                plan = build_heuristic_plan(question, schema)
                if not plan:
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
            else:
                print(f"[WhatIfPipeline] SQL planning failed: {exc}")
                plan = build_heuristic_plan(question, schema)

    if not plan:
        return {
            "sql_query": "",
            "explanation": (
                "I could not build a what-if simulation for that question. "
                "Try a concrete change with a number, e.g. “What if total sales increase by 10%?” "
                "or “What if we reduce returns by 30%?”"
            ),
            "results": [],
            "row_count": 0,
            "status": "success",
            "is_multi": False,
            "response_kind": WHAT_IF_RESPONSE_KIND,
        }

    return _build_result_from_plan(question, plan)
