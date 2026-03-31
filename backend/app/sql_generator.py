"""
sql_generator.py
----------------
Module 3 — AI SQL Generator

Converts natural language into a safe SQL SELECT + explanation using Google Gemini.
Uses LangGraph with MemorySaver so each conversation thread remembers prior Q&A
for follow-up questions ("same thing but last month", etc.).
"""

from __future__ import annotations

import json
import uuid
from typing import Annotated, Any

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from app import config


# ---------------------------------------------------------------------------
# Dangerous Input Detection
# ---------------------------------------------------------------------------

DANGEROUS_KEYWORDS = [
    "delete", "drop", "update", "insert", "truncate",
    "alter", "remove", "erase", "clear", "destroy",
    "modify", "change", "edit", "wipe",
]


def is_dangerous_input(question: str) -> bool:
    question_lower = question.lower()
    return any(keyword in question_lower for keyword in DANGEROUS_KEYWORDS)


# ---------------------------------------------------------------------------
# System prompt (schema + references); user turns live in message history
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = """You are a friendly, conversational AI assistant. Your goal is to feel natural, human-like, and easy to understand for anyone (including non-technical users). You help people explore a MySQL database: you write accurate SELECT queries and put explanations in simple, layman-friendly language.

CONTEXT — you specialize in this app's data:
* Customers
* Products
* Orders
* Line items

GREETING & SMALL TALK:
* If the user opens with ONLY a greeting or casual chat (e.g. "Hi", "Hello", "Hey", "How are you?") with no data question, do NOT generate SQL. Return JSON with "sql_query": "NOT_RELATED".
* In "explanation" for that case: respond warmly; say you're doing great (or similar) and thanks for asking; then briefly guide them toward what they can ask (customers, products, orders, line items). Keep it short — like: "Hi! I'm doing great, thanks for asking. I can help you explore your app's data — like customers, products, orders, or line items. What would you like to look into?"

RESPONSE STYLE (for all explanations):
* Conversational, polite, encouraging — like a helpful human, not a robot
* Short and easy to read; avoid unnecessary jargon
* Do not sound stiff, overly formal, or robotic
* Do not give long or complex explanations unless the user clearly asks for detail

RULES:
* Generate ONLY a SELECT query
* Never use DELETE, UPDATE, INSERT, DROP, ALTER, TRUNCATE
* Use ONLY tables and columns present in the schema
* If the question cannot be answered using the schema, return a valid SELECT query that returns an empty result
* Do not hallucinate table or column names
* If the question has NO relation to the database schema provided, do NOT generate any SQL query. Instead return this exact JSON:
  {{"sql_query": "NOT_RELATED", "explanation": "I'm focused on this app's data — things like customers, products, orders, and line items. Try asking something along those lines and I'll dig in!"}}

{references}

* Similar past queries may appear above as reference examples only — adapt SQL to the user's exact question and the schema; never copy SQL verbatim when filters, dates, or entities differ.

* If the query returns a SINGLE VALUE (e.g. COUNT, SUM, AVG, MIN, MAX — one row, one number), also include "answer_template": a natural language sentence with exactly one placeholder {{}} where the result will be inserted. Keep the tone friendly. Example: "You've got {{}} customers total." or "Last month's sales came out to {{}}."

* In "explanation" for real data questions: sound like a helpful teammate — short and natural, maybe a quick opener like "Here's what I pulled" or "Got it!" when it fits. Never use stiff phrases like "Request processed successfully" or "Your request has been completed."

* This is a multi-turn chat. Use earlier user messages and your previous JSON replies to interpret follow-ups (e.g. "same filter but for December", "narrow that down").

You must respond in ONLY this exact JSON format, nothing else:
{{
  "sql_query": "your SELECT query here",
  "explanation": "2-3 short lines in a friendly, conversational voice (or greeting guidance as above)",
  "answer_template": "Optional: one sentence with {{}} for the single result value, only for COUNT/SUM/AVG-style queries"
}}

Do not add any text before or after the JSON.
Do not use markdown, code blocks, or backticks.

Database Schema:
{schema}"""


# ---------------------------------------------------------------------------
# LangGraph state + compiled app (MemorySaver lives for process lifetime)
# ---------------------------------------------------------------------------

_MAX_MESSAGES_FOR_LLM = 24  # cap context: prior turns + current user message


class _SQLGraphState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


_llm: ChatGoogleGenerativeAI | None = None
_sql_app = None


def _get_llm() -> ChatGoogleGenerativeAI:
    global _llm
    if _llm is None:
        _llm = ChatGoogleGenerativeAI(
            model="gemini-flash-latest",
            google_api_key=config.GEMINI_API_KEY,
            temperature=0,
        )
    return _llm


def _references_to_text(references: list[dict] | None) -> str:
    if not references:
        return (
            "(No similar past queries met the similarity threshold — rely on the schema and "
            "conversation only.)"
        )
    lines = [
        "Here are some similar past queries and their solutions for reference:",
    ]
    n = 0
    for ref in references:
        past_q = (ref.get("question") or "").strip() or "(unknown)"
        past_sql = (ref.get("sql") or "").strip()
        if not past_sql:
            continue
        n += 1
        lines.append(f"Query {n}: {past_q}")
        lines.append(f"SQL {n}: {past_sql}")
    if n == 0:
        return (
            "(No similar past queries met the similarity threshold — rely on the schema and "
            "conversation only.)"
        )
    return "\n".join(lines)


def _ai_message_text(msg: AIMessage) -> str:
    c = msg.content
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts: list[str] = []
        for block in c:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("text"):
                parts.append(str(block["text"]))
        return "".join(parts)
    return str(c)


def _clean_json_response(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.splitlines()[1:])
    if cleaned.endswith("```"):
        cleaned = "\n".join(cleaned.splitlines()[:-1])
    return cleaned.strip()


def _call_model(state: _SQLGraphState, config: RunnableConfig) -> dict[str, list[AIMessage]]:
    conf = config["configurable"]
    schema = conf["schema"]
    references_text = conf["references_text"]
    system = SystemMessage(
        content=SYSTEM_PROMPT_TEMPLATE.format(schema=schema, references=references_text)
    )
    msgs = state["messages"]
    if len(msgs) > _MAX_MESSAGES_FOR_LLM:
        trimmed = msgs[-_MAX_MESSAGES_FOR_LLM:]
    else:
        trimmed = msgs
    llm = _get_llm()
    response = llm.invoke([system, *trimmed])
    if not isinstance(response, AIMessage):
        response = AIMessage(content=getattr(response, "content", str(response)))
    return {"messages": [response]}


def _build_sql_app():
    graph = StateGraph(_SQLGraphState)
    graph.add_node("generate", _call_model)
    graph.add_edge(START, "generate")
    graph.add_edge("generate", END)
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


def get_sql_app():
    global _sql_app
    if _sql_app is None:
        _sql_app = _build_sql_app()
    return _sql_app


# ---------------------------------------------------------------------------
# generate_sql_and_explanation
# ---------------------------------------------------------------------------

def generate_sql_and_explanation(
    question: str,
    schema: str,
    references: list[dict] | None = None,
    *,
    thread_id: str | None = None,
) -> dict:
    """
    Convert a natural language question into SQL + explanation.

    When ``thread_id`` is set, prior turns in that thread are loaded from
    MemorySaver so follow-up questions have context.

    Args:
        question: Current user message.
        schema: Database schema text.
        references: Optional Pinecone-style similar (question, sql) examples.
        thread_id: LangGraph checkpoint thread (conversation id). If None, a
            one-off id is used so this call does not share memory with others.
    """
    references_text = _references_to_text(references)
    tid = (thread_id or "").strip() or str(uuid.uuid4())
    app = get_sql_app()
    cfg = {
        "configurable": {
            "thread_id": tid,
            "schema": schema,
            "references_text": references_text,
        }
    }
    result = app.invoke(
        {"messages": [HumanMessage(content=question.strip())]},
        cfg,
    )
    last = result["messages"][-1]
    if not isinstance(last, AIMessage):
        raise Exception(f"Expected AIMessage, got {type(last)}")
    raw_response = _ai_message_text(last)
    cleaned = _clean_json_response(raw_response)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise Exception(
            f"Failed to parse AI response as JSON. Raw response: {raw_response}"
        ) from e
    if "sql_query" not in parsed or "explanation" not in parsed:
        raise Exception(
            f"AI response is missing required keys ('sql_query' or 'explanation'). "
            f"Got: {parsed}"
        )
    out: dict[str, Any] = {
        "sql_query": parsed["sql_query"],
        "explanation": parsed["explanation"],
    }
    if "answer_template" in parsed and parsed["answer_template"]:
        out["answer_template"] = parsed["answer_template"]
    return out
