from __future__ import annotations
import json
import uuid
from datetime import date, datetime
from decimal import Decimal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent

from app.tools.sql_tools import run_sql_query
from app import config
from app.serialization import make_json_serializable


AVAILABLE_TOOLS = [run_sql_query]


# ---------------------------------------------------------------------------
# MODULE-LEVEL LLM + COMPILED AGENT (checkpointer lives for process lifetime)
# ---------------------------------------------------------------------------
_llm: ChatGoogleGenerativeAI | None = None
_agent_app = None
_checkpointer = InMemorySaver()


def _get_llm() -> ChatGoogleGenerativeAI:
    global _llm
    if _llm is None:
        _llm = ChatGoogleGenerativeAI(
            model="gemini-flash-latest",
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
- Max 3 tool calls
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
            checkpointer=_checkpointer,
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


def _build_success_explanation(row_count: int) -> str:
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

    final_sql = ""
    final_results: list = []
    had_tool_attempt = False
    last_ai_text = ""

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
                final_sql = (data.get("sql") or "").strip()
                final_results = make_json_serializable(data.get("results") or [])
        elif isinstance(msg, AIMessage):
            last_ai_text = extract_text(msg.content)

    if final_sql and final_results is not None:
        return {
            "sql_query": final_sql,
            "explanation": _build_success_explanation(len(final_results)),
            "results": final_results,
            "row_count": len(final_results),
            "status": "success",
        }

    if had_tool_attempt:
        return {
            "sql_query": "",
            "explanation": "Sorry, could not generate a valid query. Please rephrasing.",
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
        "recursion_limit": 12,
    }

    try:
        result = app.invoke(
            {"messages": [HumanMessage(content=question.strip())]},
            cfg,
        )
    except Exception as e:
        error_str = str(e).lower()
        if "429" in error_str or "resource_exhausted" in error_str or "quota" in error_str:
            print("[AgentExecutor] Rate limit hit (429)")
            return {
                "sql_query": "",
                "explanation": "The AI service is temporarily rate-limited. Please try again shortly.",
                "results": [],
                "row_count": 0,
                "status": "rate_limited",
            }
        raise

    messages = result.get("messages") or []
    return _summarize_from_messages(messages)
