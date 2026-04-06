from __future__ import annotations
<<<<<<< Updated upstream

import json
from typing import Any

# create_agent = LangChain's built-in ReAct loop: model reasons, calls tools, reads results, repeats.
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.errors import GraphRecursionError
=======
import json
import uuid
from datetime import date, datetime
from decimal import Decimal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent
>>>>>>> Stashed changes

from app.tools.sql_tools import run_sql_query
from app import config
from app.serialization import make_json_serializable


AVAILABLE_TOOLS = [run_sql_query]
<<<<<<< Updated upstream
MAX_AGENT_ITERATIONS = 6

# Single compiled ReAct graph = one LangSmith root trace per invoke (model ↔ tools loop).
_sql_agent_graph = None


def _get_sql_react_agent_graph():
    global _sql_agent_graph
    if _sql_agent_graph is None:
        llm = ChatGoogleGenerativeAI(
=======


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
>>>>>>> Stashed changes
            model="gemini-flash-latest",
            google_api_key=config.GEMINI_API_KEY,
            temperature=0,
        )
<<<<<<< Updated upstream
        _sql_agent_graph = create_agent(
            llm,
            AVAILABLE_TOOLS,
            system_prompt=None,
            name="sql_react_agent",
        )
    return _sql_agent_graph
=======
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


def _build_success_explanation(row_count: int) -> str:
    if row_count == 0:
        return "The query ran successfully but no matching records were found."
    if row_count == 1:
        return "Got it! Here's what I found for you."
    return f"Here you go — found {row_count:,} records matching your query."
>>>>>>> Stashed changes


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


<<<<<<< Updated upstream
# ---------------------------------------------------------------------------
def _parse_tool_payload(content: Any) -> dict | None:
    if content is None:
        return None
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None
    return None


# ---------------------------------------------------------------------------
=======
>>>>>>> Stashed changes
def _build_references_text(references: list) -> str:
    if not references:
        return "No similar past queries available."

    lines = []
    for i, ref in enumerate(references[:3], 1):
        lines.append(f"Reference {i}:")
        lines.append(f"  Question: {ref.get('question', '')}")
        lines.append(f"  SQL: {ref.get('sql', '')}")
    return "\n".join(lines)


<<<<<<< Updated upstream
# ---------------------------------------------------------------------------
def _messages_to_response_dict(messages: list) -> dict:
    """Map final graph message list to the API result shape (parity with prior loop)."""
    final_sql = ""
    final_results: list = []
    final_explanation = ""
    status = "success"

    db_error_hit = False
    saw_successful_sql = False
    had_tool_message = False

    for m in messages:
        if isinstance(m, ToolMessage):
            had_tool_message = True
            data = _parse_tool_payload(m.content)
            if not isinstance(data, dict):
                continue
            if data.get("error_type") == "DB_ERROR":
                db_error_hit = True
            if data.get("success") is True:
                saw_successful_sql = True
                final_sql = data.get("sql", "") or final_sql
                final_results = make_json_serializable(data.get("results", []))

    last_ai: AIMessage | None = None
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            last_ai = m
            break

    if last_ai is not None:
        final_explanation = extract_text(last_ai.content) or ""

    if db_error_hit:
        return {
            "sql_query": "",
            "explanation": "Database is currently unavailable. Please try again later.",
            "results": [],
            "row_count": 0,
            "status": "db_error",
        }

    if not saw_successful_sql:
        if not had_tool_message and final_explanation:
            status = "not_related"
        else:
            status = "sql_error"
            if not final_explanation:
                final_explanation = "Sorry, I could not generate a valid query."
    elif not final_explanation:
        final_explanation = "Query executed successfully."

    return {
        "sql_query": final_sql,
        "explanation": final_explanation,
        "results": make_json_serializable(final_results),
        "row_count": len(final_results),
        "status": status,
    }


# ---------------------------------------------------------------------------
def generate_and_execute_with_tools(
    question: str,
    schema: str,
    references: list = None,
) -> dict:
=======
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
>>>>>>> Stashed changes


<<<<<<< Updated upstream
    system_content = f"""You are a ReAct agent: you alternate reasoning with actions (tool calls) until the user is answered.

ReAct pattern:
1. REASON — Read the message. Does it need data from this database (see schema), or is it only small talk (hi, hello, thanks)?
2. ACT — If it needs data: call the tool `run_sql_query` with a single correct SELECT. If it does NOT need data: reply in plain text only and do NOT call any tool.
3. OBSERVE — Read the tool JSON result. On success, give a short final answer to the user and stop calling tools. On VALIDATION/SQL_ERROR, fix SQL and call the tool again (limited retries). On DB_ERROR, stop and apologize without retrying.

YOUR TASK (same as above, explicit):
1. Read the user question carefully
2. If unrelated to the schema → plain text ONLY (no tool call)
3. If related → generate correct SQL → call run_sql_query

STRICT RULES:
- Max 3 tool calls
- If DB_ERROR → STOP immediately
- If SQL_ERROR → fix and retry (max 2 retries)
- After success → DO NOT call tool again
- Return ONLY short explanation (2-3 lines)

SQL RULES:
- ONLY SELECT queries
- Use ONLY given schema
- No hallucination

Database Schema:
{schema}

References:
{_build_references_text(references)}
"""

    graph = _get_sql_react_agent_graph()
    # Enough steps for several model↔tools rounds (LangGraph counts node executions).
    recursion_limit = max(25, MAX_AGENT_ITERATIONS * 4 + 8)

    try:
        result = graph.invoke(
            {
                "messages": [
                    SystemMessage(content=system_content),
                    HumanMessage(content=question),
                ]
            },
            config={"recursion_limit": recursion_limit},
        )
    except GraphRecursionError:
        print("[AgentExecutor] Recursion limit reached")
        return {
            "sql_query": "",
            "explanation": "The request took too many steps. Please try a simpler question.",
            "results": [],
            "row_count": 0,
            "status": "sql_error",
        }
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

    messages = result.get("messages", [])
    return _messages_to_response_dict(messages)
=======
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
>>>>>>> Stashed changes
