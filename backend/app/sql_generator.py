"""
sql_generator.py
----------------
Module 3 — AI SQL Generator

Converts a natural language question into a safe SQL SELECT query
and a plain-English explanation using Google Gemini via LangChain.

Main function:
    generate_sql_and_explanation(question, schema) -> dict
"""

import json

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.schema.output_parser import StrOutputParser

from app import config


# ---------------------------------------------------------------------------
# Dangerous Input Detection
# ---------------------------------------------------------------------------
# Pre-check function to detect dangerous queries before calling Gemini.
# This prevents dangerous queries from being processed by the AI model.

DANGEROUS_KEYWORDS = [
    "delete", "drop", "update", "insert", "truncate",
    "alter", "remove", "erase", "clear", "destroy",
    "modify", "change", "edit", "wipe"
]


def is_dangerous_input(question: str) -> bool:
    """
    Check if a user question contains dangerous keywords that indicate
    data modification operations.

    This function runs BEFORE calling Gemini, so dangerous queries are
    blocked immediately with a security warning instead of being processed
    by the AI model.

    Args:
        question (str): The user's natural language question.

    Returns:
        bool: True if the question contains dangerous keywords, False otherwise.
    """
    question_lower = question.lower()
    return any(keyword in question_lower for keyword in DANGEROUS_KEYWORDS)


# ---------------------------------------------------------------------------
# Prompt Template
# ---------------------------------------------------------------------------
# This is the exact instruction we send to Gemini.
# {schema} and {question} are filled in at runtime.

PROMPT_TEMPLATE = """You are an expert SQL query generator for a MySQL database.

RULES:
* Generate ONLY a SELECT query
* Never use DELETE, UPDATE, INSERT, DROP, ALTER, TRUNCATE
* Use ONLY tables and columns present in the schema
* If the question cannot be answered using the schema, return a valid SELECT query that returns an empty result
* Do not hallucinate table or column names
* If the question has NO relation to the database schema provided, do NOT generate any SQL query. Instead return this exact JSON:
  {{"sql_query": "NOT_RELATED", "explanation": "This question cannot be answered using the available database. Please ask a question related to customers, products, orders, or order items."}}

You must respond in ONLY this exact JSON format, nothing else:
{{
  "sql_query": "your SELECT query here",
  "explanation": "2-3 line simple explanation in plain English"
}}

Do not add any text before or after the JSON.
Do not use markdown, code blocks, or backticks.

Database Schema:
{schema}

User Question:
{question}"""


# ---------------------------------------------------------------------------
# generate_sql_and_explanation
# ---------------------------------------------------------------------------

def generate_sql_and_explanation(question: str, schema: str) -> dict:
    """
    Convert a natural language question into a SQL query + explanation.

    Uses Google Gemini (via LangChain) to generate a safe SELECT query
    and a short plain-English explanation of what the query does.

    Args:
        question (str): The user's natural language question.
                        e.g. "Show all customers from Pune"
        schema   (str): A text description of the database tables and columns.

    Returns:
        dict: A dictionary with two keys:
              {
                "sql_query":   "SELECT ...",
                "explanation": "This query ..."
              }

    Raises:
        Exception: If the AI response cannot be parsed as JSON, or if
                   the required keys are missing from the response.
    """

    # ------------------------------------------------------------------
    # Step 1: Build the prompt template
    # ------------------------------------------------------------------
    prompt = PromptTemplate(
        input_variables=["schema", "question"],
        template=PROMPT_TEMPLATE,
    )

    # ------------------------------------------------------------------
    # Step 2: Initialize the Gemini model
    # ------------------------------------------------------------------
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=config.GEMINI_API_KEY,
        temperature=0,          # Low temperature = more deterministic/consistent
    )

    # ------------------------------------------------------------------
    # Step 3: Build the LangChain pipeline
    # prompt → llm → plain string output
    # ------------------------------------------------------------------
    chain = prompt | llm | StrOutputParser()

    # ------------------------------------------------------------------
    # Step 4: Run the chain — send the question + schema to Gemini
    # ------------------------------------------------------------------
    raw_response = chain.invoke({
        "schema": schema,
        "question": question,
    })

    # ------------------------------------------------------------------
    # Step 5: Clean the response
    # Gemini sometimes wraps JSON in markdown fences like ```json ... ```
    # We strip those out before parsing.
    # ------------------------------------------------------------------
    cleaned = raw_response.strip()

    # Remove opening markdown fence (e.g. ```json or ```)
    if cleaned.startswith("```"):
        # Drop the first line (the fence opener)
        cleaned = "\n".join(cleaned.splitlines()[1:])

    # Remove closing markdown fence
    if cleaned.endswith("```"):
        cleaned = "\n".join(cleaned.splitlines()[:-1])

    cleaned = cleaned.strip()

    # ------------------------------------------------------------------
    # Step 6: Parse the cleaned response as JSON
    # ------------------------------------------------------------------
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        raise Exception(
            f"Failed to parse AI response as JSON. Raw response: {raw_response}"
        )

    # ------------------------------------------------------------------
    # Step 7: Validate that both required keys are present
    # ------------------------------------------------------------------
    if "sql_query" not in parsed or "explanation" not in parsed:
        raise Exception(
            f"AI response is missing required keys ('sql_query' or 'explanation'). "
            f"Got: {parsed}"
        )

    # ------------------------------------------------------------------
    # Step 8: Return the final result
    # ------------------------------------------------------------------
    return {
        "sql_query":   parsed["sql_query"],
        "explanation": parsed["explanation"],
    }