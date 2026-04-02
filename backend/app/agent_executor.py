from __future__ import annotations
from typing import List
import json
from datetime import date, datetime
from decimal import Decimal

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from app.tools.sql_tools import run_sql_query
from app import config


AVAILABLE_TOOLS = [run_sql_query]
MAX_AGENT_ITERATIONS = 6


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
        except:
            return str(obj)

    if isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [make_json_serializable(i) for i in obj]

    return obj


# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
def _build_references_text(references: list) -> str:
    if not references:
        return "No similar past queries available."

    lines = []
    for i, ref in enumerate(references[:3], 1):
        lines.append(f"Reference {i}:")
        lines.append(f"  Question: {ref.get('question', '')}")
        lines.append(f"  SQL: {ref.get('sql', '')}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
def generate_and_execute_with_tools(
    question: str,
    schema: str,
    references: list = None,
) -> dict:

    print(f"[AgentExecutor] Starting — question: {question[:80]}")

    llm = ChatGoogleGenerativeAI(
        model="gemini-flash-latest",
        google_api_key=config.GEMINI_API_KEY,
        temperature=0,
    )

    llm_with_tools = llm.bind_tools(AVAILABLE_TOOLS)

    system_content = f"""You are an expert SQL query generator for a MySQL database.

YOUR TASK:
1. Read the user question carefully
2. Check if the question relates to the database schema
3. If unrelated → respond in plain text ONLY (no tool call)
4. If related:
   - Generate correct SQL
   - Call run_sql_query

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

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=question),
    ]

    final_sql = ""
    final_results = []
    final_explanation = ""
    status = "success"
    tool_call_count = 0

    for iteration in range(MAX_AGENT_ITERATIONS):
        print(f"[AgentExecutor] Iteration {iteration + 1}/{MAX_AGENT_ITERATIONS}")

        # -------------------------------------------------------------------
        # LLM CALL (RATE LIMIT SAFE)
        # -------------------------------------------------------------------
        try:
            response = llm_with_tools.invoke(messages)
        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "resource_exhausted" in error_str or "quota" in error_str:
                print("[AgentExecutor] Rate limit hit (429)")
                return {
                    "sql_query": "",
                    "explanation": "The AI service is temporarily rate-limited. Please try again shortly.",
                    "results": [],
                    "row_count": 0,
                    "status": "rate_limited"
                }
            raise

        messages.append(response)

        if not getattr(response, "tool_calls", None):
            final_explanation = extract_text(response.content)
            if not final_sql:
                status = "not_related"
            break

        all_success = False

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_call_id = tool_call["id"]

            if tool_call_count >= 3:
                continue

            # -------------------------------------------------------------------
            # TOOL EXECUTION (SAFE)
            # -------------------------------------------------------------------
            try:
                tool_result = run_sql_query.invoke(tool_args)
            except Exception as e:
                tool_result = {
                    "success": False,
                    "error": str(e),
                    "error_type": "DB_ERROR",
                }

            # Guard
            if tool_result is None or not isinstance(tool_result, dict):
                tool_result = {
                    "success": False,
                    "error": "Tool returned an unexpected response.",
                    "error_type": "SQL_ERROR",
                }

            tool_call_count += 1

            if tool_result.get("error_type") == "DB_ERROR":
                return {
                    "sql_query": "",
                    "explanation": "Database is currently unavailable. Please try again later.",
                    "results": [],
                    "row_count": 0,
                    "status": "db_error",
                }

            if tool_result.get("success") is True:
                final_sql = tool_result.get("sql", "")
                final_results = make_json_serializable(tool_result.get("results", []))
                all_success = True

            safe_tool_result = make_json_serializable(tool_result)

            messages.append(
                ToolMessage(
                    content=json.dumps(safe_tool_result),
                    tool_call_id=tool_call_id,
                )
            )

        # -------------------------------------------------------------------
        # FINAL EXPLANATION (RATE LIMIT SAFE)
        # -------------------------------------------------------------------
        if all_success:
            try:
                final_resp = llm_with_tools.invoke(messages)
                final_explanation = extract_text(final_resp.content) or "Query executed successfully."
            except Exception as e:
                error_str = str(e).lower()
                if "429" in error_str or "resource_exhausted" in error_str:
                    final_explanation = f"Found {len(final_results)} result(s) successfully."
                else:
                    final_explanation = "Query executed successfully."

            break

    if not final_sql and status == "success":
        status = "sql_error"
        final_explanation = "Sorry, I could not generate a valid query."

    return {
        "sql_query": final_sql,
        "explanation": final_explanation,
        "results": make_json_serializable(final_results),
        "row_count": len(final_results),
        "status": status,
    }