from __future__ import annotations
import json
import uuid
from typing import Any

# pyrefly: ignore [missing-import]
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
# pyrefly: ignore [missing-import]
from langchain_core.runnables import RunnableConfig, RunnableLambda
# pyrefly: ignore [missing-import]
from langchain_google_genai import ChatGoogleGenerativeAI
# pyrefly: ignore [missing-import]
from langgraph.prebuilt import create_react_agent

from app.tools.sql_tools import run_sql_query, render_chart
from app import config
from app.checkpointer import get_checkpointer
from app.llm_errors import rate_limited
from app.serialization import make_json_serializable
from app.response_formatting import (
    build_result_sentence,
    build_results_narrative,
    merge_explanation_with_narrative,
)
from app.question_planner import build_question_plan
from app.query_validator import validate_sql, QueryValidationError
from app.database import execute_query, select_sql_with_row_limit
from app.memory.pipeline import (
    apply_hybrid_message_view,
    build_memory_preamble_for_system,
    maybe_refresh_thread_memory_after_turn,
)


AVAILABLE_TOOLS = [run_sql_query, render_chart]


# ---------------------------------------------------------------------------
# MODULE-LEVEL LLM + COMPILED AGENT (shared Postgres or in-memory checkpointer)
# ---------------------------------------------------------------------------
_llm: ChatGoogleGenerativeAI | None = None
_agent_app = None


def _get_llm() -> ChatGoogleGenerativeAI:
    global _llm
    if _llm is None:
        _llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=config.GEMINI_API_KEY,
            temperature=0,
        )
    return _llm


def _prepend_system(state: dict, config: RunnableConfig) -> list:
    conf = config.get("configurable") or {}
    schema = conf.get("schema") or ""
    references_text = conf.get("references_text") or "No similar past queries available."
    plan_json = conf.get("plan_json") or "{}"
    tid = (conf.get("thread_id") or "").strip()
    memory_block = build_memory_preamble_for_system(tid)
    try:
        plan = json.loads(plan_json)
        chart_hint = plan.get("chart_hint")
        needs_chart = bool(plan.get("needs_chart")) and chart_hint in ("pie", "bar", "line")
    except Exception:
        chart_hint = None
        needs_chart = False

    chart_instruction = ""
    if needs_chart and chart_hint:
        chart_instruction = f"""
- PLANNER INSTRUCTION: Visualize results as a {chart_hint.upper()} chart. You MUST use the `render_chart` tool in TWO SEQUENTIAL STEPS:
  Step 1: Call `run_sql_query` first and wait for the result.
  Step 2: After seeing the SQL result, call `render_chart` with chart_type="{chart_hint}", x_column=<exact axis/category/time column>, y_column=<exact numeric column> from those rows. If the user compares two numeric series over the same x (e.g. successful vs failed by day), rewrite SQL to one row per x with TWO numeric columns (SUM CASE / pivot), then pass the second column as y_column_2 — do NOT refuse a chart because rows are long-format; reshape the query instead.
  DO NOT put chart arguments into `run_sql_query`, and DO NOT call `run_sql_query` and `render_chart` at the same time before you have row data.
  Chart choice: use chart_type "pie" only for part-to-whole / shares; "bar" for rankings or comparing categories; "line" for trends or time-ordered series (x_column = time or order dimension).
"""

    system_content = f"""You are an expert SQL query generator for a MySQL database.

YOUR TASK:
1. Read the user question carefully (including earlier turns in this conversation)
2. Read and follow the planner metadata exactly when deciding strategy.
3. Check if the question relates to the database schema
4. If unrelated → respond in plain text ONLY (no tool call). Remember personal facts the user stated (e.g. their name) and answer follow-ups from conversation memory.
5. If related:
   - Generate correct SQL
   - Call run_sql_query

STRICT RULES:
- If the user explicitly asks for a bar chart, line chart, pie chart, or time-series plot, call `render_chart` immediately after a successful `run_sql_query` for that dataset, using chart_type bar/line/pie and exact column names from the rows.
- For "A vs B" / two metrics over time or category: return ONE pivoted query (one x, two numeric columns) and one `render_chart` with y_column and y_column_2. Do not claim charts are impossible because of long-format (date,status,count) data — pivot with conditional aggregation, then chart.
- Max 6 tool calls
- If the user asks for multiple distinct datasets or questions (e.g. 'How many customers and what are the top 3 products?'), you MUST explicitly make MULTIPLE PARALLEL tool calls at the exact same time by outputting an array with multiple run_sql_query calls. Do not process them one by one.{chart_instruction}
- If DB_ERROR → STOP immediately
- If SQL_ERROR → fix and retry (max 2 retries)
- After successfully executing queries, provide your final response based on the planner strategy:
   * IF 'strategic_mode': You MUST act as a senior data analyst. Review the data returned, identify trends/anomalies, and provide a DETAILED, ACTIONABLE recommendation (at least 2-3 detailed paragraphs). Explain the 'why' behind the numbers and what the business should do next. Do NOT be concise; provide depth and insight.
   * OTHERWISE: Keep the final explanation concise (typically 2-5 lines).
- Never return raw numbers without context; explain what each value represents.
- If multiple values are returned, label each value clearly.
- Do not mention memory/cache retrieval unless the user explicitly asks.
- If one part fails, still report successful parts.

SQL RULES:
- ONLY SELECT queries
- Use ONLY given schema
- No hallucination
- Target dialect is MySQL/TiDB only
- For month-wise grouping, use MySQL date functions such as DATE_FORMAT(order_date, '%Y-%m'), MONTH(order_date), YEAR(order_date)
- Never use SQLite/Postgres-only functions like strftime or date_trunc
- For cross-table constraints (e.g., demand + stock), use proper joins or CTEs
{memory_block}

PLANNER METADATA (JSON):
{plan_json}

Database Schema:
{schema}

References:
{references_text}
"""
    raw = state.get("messages") or []
    msgs = apply_hybrid_message_view(raw, config)
    return [SystemMessage(content=system_content)] + msgs


def _get_agent_app():
    global _agent_app
    if _agent_app is None:
        _agent_app = create_react_agent(
            _get_llm(),
            tools=AVAILABLE_TOOLS,
            prompt=RunnableLambda(_prepend_system),
            checkpointer=get_checkpointer(),
            version="v2",
        )
    return _agent_app


# ---------------------------------------------------------------------------
def _build_success_explanation(row_count: int) -> str:
    """
    Return a concise, human-friendly explanation without an extra LLM call.
    Saves ~15-20s by skipping the second agent iteration after tool success.
    """
    if row_count == 0:
        return "The query ran successfully but no matching records were found."
    if row_count == 1:
        return "Got it! Here's what I found for you."
    return f"Here you go — found {row_count:,} records matching your query."


def extract_text(content):
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict) and "text" in item:
                texts.append(item["text"])
        return " ".join(texts)

    return str(content)


def _build_references_text(references: list) -> str:
    if not references:
        return "No similar past queries available."

    lines = []
    for i, ref in enumerate(references[:3], 1):
        lines.append(f"Reference {i}:")
        lines.append(f"  Question: {ref.get('question', '')}")
        lines.append(f"  SQL: {ref.get('sql', '')}")
    return "\n".join(lines)


def _parse_tool_content(msg: ToolMessage) -> dict:
    raw = msg.content
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        import ast
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, dict):
                return parsed
            return {}
        except (ValueError, SyntaxError):
            return {}


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


def _build_sub_response(question: str, data: dict[str, Any]) -> dict[str, Any]:
    rows = make_json_serializable(data.get("results") or [])
    if not isinstance(rows, list):
        rows = [rows]
    narrative = build_results_narrative(rows) or "This section contains the query output details."
    sentence = build_result_sentence(rows, None) or ""
    return {
        "question": question,
        "sql": (data.get("sql") or "").strip(),
        "explanation": narrative,
        "results": rows,
        "row_count": len(rows),
        "result_sentence": sentence,
        "cache_references": [],
        "status": "success",
        "cache_doc_id": None,
        "chart_config": None,
    }



def _last_human_index(messages: list) -> int:
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return i
    return -1


def _summarize_from_messages(messages: list) -> dict:
    """Derive sql_query, results, explanation, status from graph message history for this turn."""
    idx = _last_human_index(messages)
    tail = messages[idx + 1 :] if idx >= 0 else messages

    had_tool_attempt = False
    last_ai_text = ""
    successful_tools = []
    failed_tools = []
    chart_configs: list[dict[str, Any]] = []

    for msg in tail:
        if isinstance(msg, ToolMessage):
            had_tool_attempt = True
            data = _parse_tool_content(msg)
            if data.get("error_type") == "DB_ERROR":
                return {
                    "sql_query": "",
                    "explanation": "Database is currently unavailable. Please try again later.",
                    "results": [],
                    "row_count": 0,
                    "status": "db_error",
                }
            if data.get("success") is True:
                if data.get("chart_type") in ("pie", "bar", "line"):
                    cfg_entry: dict[str, Any] = {
                        "chart_type": data["chart_type"],
                        "x_column": data.get("x_column"),
                        "y_column": data.get("y_column"),
                        "is_pie_chart": data["chart_type"] == "pie",
                    }
                    y2 = data.get("y_column_2")
                    if isinstance(y2, str) and y2.strip():
                        cfg_entry["y_column_2"] = y2.strip()
                    chart_configs.append(cfg_entry)
                elif data.get("is_pie_chart") is True:
                    # Legacy tool payloads (label/value only)
                    chart_configs.append(
                        {
                            "chart_type": "pie",
                            "x_column": data.get("label_column"),
                            "y_column": data.get("value_column"),
                            "is_pie_chart": True,
                        }
                    )
                else:
                    successful_tools.append(data)
            elif data.get("error"):
                failed_tools.append(data)
        elif isinstance(msg, AIMessage):
            txt = extract_text(msg.content).strip()
            if txt:
                last_ai_text = txt

    def _find_matching_chart(rows, configs):
        if not rows or not configs:
            return None
        first_row = rows[0]
        for conf in configs:
            xc = conf.get("x_column")
            yc = conf.get("y_column")
            if xc not in first_row or yc not in first_row:
                continue
            y2 = conf.get("y_column_2")
            if isinstance(y2, str) and y2.strip():
                if y2.strip() not in first_row:
                    continue
            return conf
        return None

    if len(successful_tools) == 1 and not failed_tools:
        data = successful_tools[0]
        rows = make_json_serializable(data.get("results") or [])
        if not isinstance(rows, list):
            rows = [rows]

        narrative = build_results_narrative(rows)
        explanation = merge_explanation_with_narrative(last_ai_text.strip(), narrative)
        if not explanation:
            explanation = _build_success_explanation(len(rows))

        return {
            "sql_query": (data.get("sql") or "").strip(),
            "explanation": explanation,
            "results": rows,
            "row_count": len(rows),
            "status": "success",
            "is_multi": False,
            "chart_config": _find_matching_chart(rows, chart_configs),
        }

    elif len(successful_tools) > 1 or (successful_tools and failed_tools):
        sub_responses = []
        for i, data in enumerate(successful_tools):
            rows = make_json_serializable(data.get("results") or [])
            if not isinstance(rows, list):
                rows = [rows]
            narrative = build_results_narrative(rows) or "This section contains the query output details."
            result_sentence = build_result_sentence(rows, None) or ""
            sub_responses.append({
                "question": f"Result {i + 1}",
                "sql": (data.get("sql") or "").strip(),
                "explanation": narrative,
                "results": rows,
                "row_count": len(rows),
                "result_sentence": result_sentence,
                "cache_references": [],
                "status": "success",
                "cache_doc_id": None,
                "chart_config": _find_matching_chart(rows, chart_configs),
            })

        for i, data in enumerate(failed_tools):
            err_sql = (data.get("sql") or "").strip()
            err_text = (data.get("error") or "Query failed.").strip()
            sub_responses.append(
                {
                    "question": f"Result {len(successful_tools) + i + 1}",
                    "sql": err_sql,
                    "explanation": f"I could not run this part of the request: {err_text}",
                    "results": [],
                    "row_count": 0,
                    "result_sentence": "",
                    "cache_references": [],
                    "status": data.get("error_type", "sql_error").lower(),
                    "cache_doc_id": None,
                    "chart_config": None,
                }
            )
        return {
            "sql_query": "",
            "explanation": last_ai_text.strip() or (
                f"I processed {len(successful_tools)} part(s) of your request successfully. "
                "Any part that could not be executed is clearly labeled below with the reason."
            ),
            "results": [],
            "row_count": 0,
            "status": "success",
            "is_multi": True,
            "sub_responses": sub_responses
        }

    if had_tool_attempt:
        return {
            "sql_query": "",
            "explanation": "Sorry, could not generate a valid query. Please try rephrasing.",
            "results": [],
            "row_count": 0,
            "status": "sql_error",
        }

    return {
        "sql_query": "",
        "explanation": last_ai_text or "I'm not sure how to help with that.",
        "results": [],
        "row_count": 0,
        "status": "not_related",
    }


def generate_and_execute_with_tools(
    question: str,
    schema: str,
    references: list | None = None,
    *,
    thread_id: str | None = None,
) -> dict:
    print(f"[AgentExecutor] Starting — question: {question[:80]}")

    references_text = _build_references_text(references or [])
    plan = build_question_plan(question, schema)
    print(
        "[Planner] "
        + json.dumps(
            {
                "intents": plan.get("intents", []),
                "strategy": plan.get("strategy"),
                "assumptions": plan.get("assumptions", []),
            }
        )
    )

    if plan.get("strategy") == "deterministic_sql":
        sql_blocks = plan.get("deterministic_sql") or []
        if sql_blocks:
            responses = []
            failures = []
            for idx, sql in enumerate(sql_blocks):
                data = _execute_safe_sql(sql)
                if data.get("success"):
                    responses.append(_build_sub_response(f"Result {idx + 1}", data))
                else:
                    failures.append(data)
            if responses and not failures:
                first = responses[0]
                explanation = first["explanation"]
                if plan.get("assumptions"):
                    explanation = (
                        f"{explanation}\n\nAssumption used: {plan['assumptions'][0]}"
                    )
                return {
                    "sql_query": first.get("sql", ""),
                    "explanation": explanation,
                    "results": first.get("results", []),
                    "row_count": first.get("row_count", 0),
                    "status": "success",
                    "is_multi": False,
                }
            if responses:
                return {
                    "sql_query": "",
                    "explanation": "I answered the available parts and labeled any failed parts below.",
                    "results": [],
                    "row_count": 0,
                    "status": "success",
                    "is_multi": True,
                    "sub_responses": responses
                    + [
                        {
                            "question": "Failed result",
                            "sql": f.get("sql", ""),
                            "explanation": f"I could not run this part: {f.get('error', 'Unknown error')}",
                            "results": [],
                            "row_count": 0,
                            "result_sentence": "",
                            "cache_references": [],
                            "status": (f.get("error_type") or "sql_error").lower(),
                            "cache_doc_id": None,
                            "chart_config": None,
                        }
                        for f in failures
                    ],
                }

    tid = (thread_id or "").strip() or str(uuid.uuid4())
    app = _get_agent_app()
    cfg: RunnableConfig = {
        "configurable": {
            "thread_id": tid,
            "schema": schema,
            "references_text": references_text,
            "plan_json": json.dumps(plan),
        },
        "recursion_limit": 15,
    }

    try:
        result = app.invoke(
            {"messages": [HumanMessage(content=question.strip())]},
            cfg,
        )
    except Exception as e:
        error_str = str(e).lower()
        if rate_limited(e):
            print(f"[AgentExecutor] Quota limit hit: {error_str}")
            return {
                "sql_query": "",
                "explanation": "The AI service quota has been reached (429 Resource Exhausted). Please wait a few minutes or try again later.",
                "results": [],
                "row_count": 0,
                "status": "rate_limited",
            }
        # Log and re-raise other unexpected errors
        print(f"[AgentExecutor] Unexpected error: {error_str}")
        raise

    messages = result.get("messages") or []
    maybe_refresh_thread_memory_after_turn(tid, messages)
    summary = _summarize_from_messages(messages)
    if summary.get("status") == "success" and plan.get("assumptions"):
        summary["explanation"] = (
            f"{summary.get('explanation', '').strip()}\n\nAssumption used: {plan['assumptions'][0]}"
        ).strip()
    return summary
