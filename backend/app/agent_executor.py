from __future__ import annotations
import json
import uuid
from datetime import date, datetime
from decimal import Decimal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from app.tools.sql_tools import run_sql_query, render_pie_chart
from app import config
from app.checkpointer import get_checkpointer
from app.serialization import make_json_serializable


AVAILABLE_TOOLS = [run_sql_query, render_pie_chart]


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
    system_content = f"""You are an expert SQL query generator for a MySQL database.

YOUR TASK:
1. Read the user question carefully (including earlier turns in this conversation)
2. Check if the question relates to the database schema
3. If unrelated → respond in plain text ONLY (no tool call). Remember personal facts the user stated (e.g. their name) and answer follow-ups from conversation memory.
4. If related:
   - Generate correct SQL
   - Call run_sql_query

STRICT RULES:
- Max 6 tool calls
- If the user asks for multiple distinct datasets or questions (e.g. 'How many customers and what are the top 3 products?'), you MUST explicitly make MULTIPLE PARALLEL tool calls at the exact same time by outputting an array with multiple run_sql_query calls. Do not process them one by one.
- If the result inherently makes sense as a PIE CHART (e.g. visualizing distribution, percentages, parts of a whole, group by counts/sums), you MUST explicitly make PARALLEL tool calls to BOTH `run_sql_query` AND `render_pie_chart` at the exact same time. You do not need the user to explicitly say 'pie chart'. For `render_pie_chart`, provide the correct `label_column` and `value_column` matching exactly what your SQL returns.
- If DB_ERROR → STOP immediately
- If SQL_ERROR → fix and retry (max 2 retries)
- After success → you may give a short explanation in plain text (no further tool calls needed)
- Return ONLY short explanation (2-3 lines) when finishing

SQL RULES:
- ONLY SELECT queries
- Use ONLY given schema
- No hallucination

Database Schema:
{schema}

References:
{references_text}
"""
    msgs = state.get("messages") or []
    return [SystemMessage(content=system_content)] + list(msgs)


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
# SERIALIZER
# ---------------------------------------------------------------------------
def make_json_serializable(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()

    if isinstance(obj, Decimal):
        return float(obj)

    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8")
        except Exception:
            return str(obj)

    if isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [make_json_serializable(i) for i in obj]

    return obj


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
            if isinstance(item, dict) and "text" in item:
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
        return {}


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
    pie_chart_config = None

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
                if data.get("is_pie_chart") is True:
                    pie_chart_config = {
                        "is_pie_chart": True,
                        "label_column": data.get("label_column"),
                        "value_column": data.get("value_column"),
                    }
                else:
                    successful_tools.append(data)
        elif isinstance(msg, AIMessage):
            last_ai_text = extract_text(msg.content)

    if len(successful_tools) == 1:
        data = successful_tools[0]
        rows = make_json_serializable(data.get("results") or [])
        if not isinstance(rows, list):
            rows = [rows]
        return {
            "sql_query": (data.get("sql") or "").strip(),
            "explanation": _build_success_explanation(len(rows)),
            "results": rows,
            "row_count": len(rows),
            "status": "success",
            "is_multi": False,
            "chart_config": pie_chart_config,
        }

    elif len(successful_tools) > 1:
        sub_responses = []
        for i, data in enumerate(successful_tools):
            rows = make_json_serializable(data.get("results") or [])
            if not isinstance(rows, list):
                rows = [rows]
            sub_responses.append({
                "question": f"Query Result {i+1}",
                "sql": (data.get("sql") or "").strip(),
                "explanation": "Query executed successfully.",
                "results": rows,
                "row_count": len(rows),
                "result_sentence": "",
                "cache_references": [],
                "status": "success",
                "cache_doc_id": None,
                "chart_config": pie_chart_config if i == 0 else None
            })
        return {
            "sql_query": "",
            "explanation": last_ai_text or f"I successfully ran {len(successful_tools)} queries for you. Here are the results:",
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
    tid = (thread_id or "").strip() or str(uuid.uuid4())
    app = _get_agent_app()
    cfg: RunnableConfig = {
        "configurable": {
            "thread_id": tid,
            "schema": schema,
            "references_text": references_text,
        },
        "recursion_limit": 4,
    }

    try:
        result = app.invoke(
            {"messages": [HumanMessage(content=question.strip())]},
            cfg,
        )
    except Exception as e:
        error_str = str(e).lower()
        # Explicit check for 429 / Quota / Resource Exhausted
        if any(k in error_str for k in ("429", "resource_exhausted", "quota")):
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
    return _summarize_from_messages(messages)
