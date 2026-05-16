"""
Quota-efficient pipeline for analytical / advisory questions.

Uses two small LLM calls (SQL planning + synthesis) instead of a multi-turn ReAct loop
with up to three tool rounds and long prose generation.
"""

from __future__ import annotations

import json
import re
from typing import Any

# pyrefly: ignore [missing-import]
from langchain_core.messages import HumanMessage, SystemMessage
# pyrefly: ignore [missing-import]
from langchain_google_genai import ChatGoogleGenerativeAI

from app import config
from app.database import execute_query, select_sql_with_row_limit
from app.llm_errors import invoke_with_retry, rate_limited
from app.query_validator import QueryValidationError, validate_sql
from app.serialization import make_json_serializable

_STRATEGIC_MODEL = "gemini-2.5-flash-lite"
_MAX_SQL_QUERIES = 2
_MAX_ROWS_PER_QUERY = 20
STRATEGIC_RESPONSE_KIND = "strategic_advisory"


def is_strategic_advisory_result(tool_result: dict[str, Any]) -> bool:
    return (tool_result or {}).get("response_kind") == STRATEGIC_RESPONSE_KIND


def should_use_strategic_pipeline(question: str, plan: dict[str, Any]) -> bool:
    if plan.get("strategy") == "strategic_mode":
        return True
    ql = (question or "").lower()
    advisory = (
        "how can",
        "how do",
        "how should",
        "how to",
        "what can",
        "what should",
        "ways to",
        "help me",
        "recommend",
        "suggest",
    )
    topics = (
        "sales",
        "profit",
        "revenue",
        "returns",
        "churn",
        "margin",
        "delivery",
        "stock",
        "price",
        "pricing",
        "customer",
        "product",
        "competitor",
        "satisfaction",
        "loss",
        "underperform",
    )
    return any(p in ql for p in advisory) and any(t in ql for t in topics)


def _get_strategic_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=_STRATEGIC_MODEL,
        google_api_key=config.GEMINI_API_KEY,
        temperature=0,
    )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _execute_safe_sql(sql: str) -> dict[str, Any]:
    try:
        validated = validate_sql(sql)
    except QueryValidationError as e:
        return {"success": False, "error": str(e), "error_type": "VALIDATION", "sql": sql}

    res = execute_query(validated)
    if isinstance(res, dict) and "error" in res:
        return {
            "success": False,
            "error": str(res["error"]),
            "error_type": "SQL_ERROR",
            "sql": validated,
        }
    rows = make_json_serializable(res if isinstance(res, list) else [res])
    return {
        "success": True,
        "results": rows,
        "row_count": len(rows),
        "sql": select_sql_with_row_limit(validated),
    }


def _truncate_rows(rows: list[Any], limit: int = _MAX_ROWS_PER_QUERY) -> list[Any]:
    if not isinstance(rows, list):
        return []
    return rows[:limit]


def _plan_sql_queries(
    question: str,
    schema: str,
    references_text: str,
) -> list[str]:
    llm = _get_strategic_llm()
    prompt = f"""You plan read-only SQL for a business analytics question.

Return ONLY valid JSON (no markdown):
{{"queries": ["SELECT ...", ...]}}

Rules:
- At most {_MAX_SQL_QUERIES} SELECT queries for MySQL/TiDB
- Use ONLY tables/columns from the schema below
- No INSERT/UPDATE/DELETE
- Prefer focused aggregates (GROUP BY, ORDER BY, LIMIT) over wide dumps
- If one query is enough, return a single-element array

Question: {question.strip()}

Schema:
{schema}

Similar past queries (hints only):
{references_text or "None"}
"""
    response = invoke_with_retry(
        lambda: llm.invoke([HumanMessage(content=prompt)]),
    )
    content = response.content
    if isinstance(content, list):
        content = " ".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    payload = _extract_json_object(str(content))
    if not payload:
        return []

    raw_queries = payload.get("queries") or payload.get("sql") or []
    if isinstance(raw_queries, str):
        raw_queries = [raw_queries]
    if not isinstance(raw_queries, list):
        return []

    out: list[str] = []
    for item in raw_queries:
        if not isinstance(item, str):
            continue
        sql = item.strip().rstrip(";")
        if not sql:
            continue
        try:
            validate_sql(sql)
        except QueryValidationError:
            continue
        out.append(sql)
        if len(out) >= _MAX_SQL_QUERIES:
            break
    return out


def _synthesize_recommendation(
    question: str,
    evidence: list[dict[str, Any]],
    assumptions: list[str],
) -> str:
    llm = _get_strategic_llm()
    assumption_block = ""
    if assumptions:
        assumption_block = "\nAssumptions:\n" + "\n".join(f"- {a}" for a in assumptions)

    prompt = f"""You are a senior retail/data analyst. Using ONLY the evidence below, answer the user's question with clear, actionable recommendations.

Write 2 short paragraphs:
1) What the data shows (specific numbers where available)
2) What the business should do next (concrete actions)

Do not invent metrics that are not in the evidence. If evidence is empty, say what data is missing and suggest one follow-up query.

Question: {question.strip()}
{assumption_block}

Evidence (JSON):
{json.dumps(evidence, default=str)[:12000]}
"""
    response = invoke_with_retry(
        lambda: llm.invoke(
            [
                SystemMessage(
                    content="Respond in plain English. No SQL in the answer. Be specific and practical."
                ),
                HumanMessage(content=prompt),
            ]
        ),
    )
    content = response.content
    if isinstance(content, list):
        content = " ".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return (str(content) or "").strip() or (
        "I gathered data for your question but could not generate a summary. Please try again."
    )


def execute_strategic_pipeline(
    question: str,
    schema: str,
    references_text: str = "",
    *,
    assumptions: list[str] | None = None,
) -> dict[str, Any] | None:
    """
    Run the two-phase strategic pipeline.

    Returns a result dict compatible with ``generate_and_execute_with_tools``, or
    ``None`` to fall back to the full ReAct agent.
    """
    try:
        sql_queries = _plan_sql_queries(question, schema, references_text)
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
        print(f"[StrategicPipeline] SQL planning failed: {exc}")
        return None

    if not sql_queries:
        return None

    evidence: list[dict[str, Any]] = []
    executed_sql: list[str] = []
    for sql in sql_queries:
        data = _execute_safe_sql(sql)
        executed_sql.append(data.get("sql") or sql)
        if not data.get("success"):
            evidence.append(
                {
                    "sql": data.get("sql") or sql,
                    "error": data.get("error"),
                    "rows": [],
                }
            )
            continue
        rows = make_json_serializable(data.get("results") or [])
        if not isinstance(rows, list):
            rows = [rows]
        evidence.append(
            {
                "sql": data.get("sql") or sql,
                "row_count": len(rows),
                "rows": _truncate_rows(rows),
            }
        )

    # Synthesize even when queries return zero rows — the model can still advise from schema gaps.
    if not evidence:
        return None

    try:
        explanation = _synthesize_recommendation(
            question,
            evidence,
            assumptions or [],
        )
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
        print(f"[StrategicPipeline] Synthesis failed: {exc}")
        return None

    if assumptions:
        explanation = (
            f"{explanation}\n\nAssumption used: {assumptions[0]}"
        ).strip()

    return {
        "sql_query": ";\n".join(executed_sql),
        "explanation": explanation,
        "results": [],
        "row_count": 0,
        "status": "success",
        "is_multi": False,
        "response_kind": STRATEGIC_RESPONSE_KIND,
    }
