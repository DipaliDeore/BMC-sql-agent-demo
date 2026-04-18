"""
fix_sql_tool.py
---------------
Helper tool that asks Gemini to repair a broken SQL SELECT query.
The function is defensive: if anything fails, it returns the original SQL.
"""

from __future__ import annotations

import json

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from app import config


FIX_SQL_PROMPT = """You are an expert SQL query fixer for a MySQL database.

A SQL query was executed and failed with an error.
Your job is to fix the query.

RULES:
- Generate ONLY a SELECT query
- Never use DELETE, UPDATE, INSERT, DROP, ALTER, TRUNCATE
- Use ONLY tables and columns from the schema below
- Do not hallucinate column or table names

You must respond in ONLY this exact JSON format, nothing else:
{{
  "sql_query": "your corrected SELECT query here"
}}

Do not add any text before or after the JSON.
Do not use markdown or backticks.

Database Schema:
{schema}

User Question:
{question}

Previous (broken) SQL:
{previous_sql}

Error Message:
{error_message}
"""


def _clean_json_response(raw: str) -> str:
    """
    Remove optional markdown code fences from model output.
    This mirrors the cleanup behavior used in sql_generator.py.
    """
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.splitlines()[1:])
    if cleaned.endswith("```"):
        cleaned = "\n".join(cleaned.splitlines()[:-1])
    return cleaned.strip()


def fix_sql_query(question: str, previous_sql: str, error_message: str, schema: str) -> str:
    """
    Ask Gemini to fix a broken SQL query and return the corrected SQL string.

    Steps:
    1) Build a strict prompt with schema, question, prior SQL, and DB error.
    2) Invoke Gemini with deterministic settings (temperature=0).
    3) Parse JSON and return parsed["sql_query"].
    4) On any exception, return previous_sql unchanged.
    """
    # Always keep a safe fallback to avoid breaking the request flow.
    fallback_sql = previous_sql

    try:
        # Build the same model family used by sql_generator.py.
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=config.GEMINI_API_KEY,
            temperature=0,
        )

        # Create a prompt template and a simple string output parser.
        prompt = PromptTemplate.from_template(FIX_SQL_PROMPT)
        parser = StrOutputParser()
        chain = prompt | llm | parser

        # Invoke model with concrete runtime values.
        raw_response = chain.invoke(
            {
                "schema": schema,
                "question": question,
                "previous_sql": previous_sql,
                "error_message": error_message,
            }
        )

        # Clean optional markdown fences and parse strict JSON payload.
        cleaned = _clean_json_response(raw_response)
        parsed = json.loads(cleaned)

        # Extract SQL query key; if empty, fall back to original SQL.
        fixed_sql = str(parsed.get("sql_query", "")).strip()
        return fixed_sql or fallback_sql
    except Exception:
        # Defensive fallback: never crash retry flow due to fixer failures.
        return fallback_sql

