"""
query_analyzer.py
-----------------
Uses Gemini to detect whether a user message contains multiple independent
database questions. Results are cached in-memory to avoid repeated LLM calls.
"""

import json

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from app import config

# ---------------------------------------------------------------------------
# MODULE-LEVEL LLM SINGLETON (avoids per-request re-initialization overhead)
# ---------------------------------------------------------------------------
_analyzer_llm: ChatGoogleGenerativeAI | None = None


def _get_analyzer_llm() -> ChatGoogleGenerativeAI:
    global _analyzer_llm
    if _analyzer_llm is None:
        _analyzer_llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=config.GEMINI_API_KEY,
            temperature=0,
        )
    return _analyzer_llm


# Simple in-memory cache with size limit
# Key: normalized question string
# Value: analysis result dict
_query_cache = {}


# Prompt template: instructs the model to return strict JSON only.
ANALYZER_PROMPT = """You are a query analyzer for a MySQL database assistant.

Analyze if this user question contains MULTIPLE INDEPENDENT database queries.

RULES:
- Split whenever user asks for multiple distinct pieces of information
- If the question is "Show me A and B", split it into two queries
- If one query needs data from another → return SINGLE
- Maximum {max_sub_queries} sub-queries allowed (hard limit)
- Each sub-query must be meaningful and standalone

You must respond in ONLY this exact JSON format, nothing else:
{{
  "type": "SINGLE",
  "queries": ["original question here"]
}}
OR
{{
  "type": "MULTI",
  "queries": ["sub-query 1", "sub-query 2"]
}}
OR
{{
  "type": "AMBIGUOUS",
  "queries": ["original question here"]
}}

Do not add any text before or after the JSON.
Do not use markdown or backticks.

Database Schema:
{schema}

User Question:
{question}"""


def _validate_analysis(parsed: dict, original_question: str) -> dict:
    """
    Validate LLM output and return a safe result.
    Any issue → return SINGLE with the original question only.
    """
    # Check required fields exist
    if "type" not in parsed or "queries" not in parsed:
        print("[QueryAnalyzer] Missing fields — fallback to SINGLE")
        return {"type": "SINGLE", "queries": [original_question]}

    # If LLM said SINGLE → trust it
    if parsed["type"] == "SINGLE":
        return {"type": "SINGLE", "queries": [original_question]}

    # If LLM said AMBIGUOUS → treat as SINGLE
    if parsed["type"] == "AMBIGUOUS":
        return {"type": "SINGLE", "queries": [original_question]}

    # If MULTI → validate sub-queries
    if parsed["type"] == "MULTI":
        queries = parsed["queries"]
        if not isinstance(queries, list):
            print("[QueryAnalyzer] queries is not a list — fallback to SINGLE")
            return {"type": "SINGLE", "queries": [original_question]}

        # Step A: Clean first — remove empty/whitespace strings
        queries = [q.strip() for q in queries if q and str(q).strip()]

        # Step B: Deduplicate — case-insensitive, preserve original order
        seen = set()
        unique_queries = []
        for q in queries:
            if q.lower() not in seen:
                seen.add(q.lower())
                unique_queries.append(q)
        queries = unique_queries

        # Step C: Enforce max limit AFTER cleaning
        queries = queries[: config.MAX_SUB_QUERIES]

        # Step D: Need at least 2 queries to be MULTI
        if len(queries) < 2:
            print("[QueryAnalyzer] Less than 2 valid queries — fallback to SINGLE")
            return {"type": "SINGLE", "queries": [original_question]}

        return {"type": "MULTI", "queries": queries}

    # Unknown type → SINGLE
    print("[QueryAnalyzer] Unknown type field — fallback to SINGLE")
    return {"type": "SINGLE", "queries": [original_question]}


def analyze_query(question: str, schema: str, preference: str = "AUTO") -> dict:
    """
    Analyze if user question contains multiple independent queries.

    Returns:
        {"type": "SINGLE"|"MULTI"|"AMBIGUOUS", "queries": [...]}

    Always falls back to SINGLE if anything goes wrong.
    """
    try:
        # Step 1: Normalize question for cache key
        normalized_q = f"{preference}:{question.strip().lower()}"

        # Step 2: Check cache first — avoid repeated LLM calls
        if normalized_q in _query_cache:
            print("[QueryAnalyzer] Cache hit — returning cached result")
            return _query_cache[normalized_q]

        # Step 3: Call LLM
        prompt_template = ANALYZER_PROMPT
        if preference == "MULTI":
            prompt_template += "\n\nCRITICAL INSTRUCTION: The user has EXPLICITLY requested to treat this as multiple queries. You MUST return a 'MULTI' JSON response and split the question into reasonable sub-queries. Do NOT return 'AMBIGUOUS' or 'SINGLE' unless it is absolutely impossible to split."

        prompt = PromptTemplate(
            input_variables=["schema", "question", "max_sub_queries"],
            template=prompt_template,
        )
        llm = _get_analyzer_llm()  # Cached singleton — no re-init overhead
        chain = prompt | llm | StrOutputParser()
        raw_response = chain.invoke(
            {
                "schema": schema,
                "question": question,
                "max_sub_queries": config.MAX_SUB_QUERIES,
            }
        )

        # Step 4: Clean markdown fences (same pattern as sql_generator.py)
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(cleaned.splitlines()[1:])
        if cleaned.endswith("```"):
            cleaned = "\n".join(cleaned.splitlines()[:-1])
        cleaned = cleaned.strip()

        # Step 5: Parse JSON — catch invalid JSON before anything else
        try:
            parsed = json.loads(cleaned)
        except Exception:
            print("[QueryAnalyzer] Invalid JSON from LLM — fallback to SINGLE")
            return {"type": "SINGLE", "queries": [question]}

        # Step 6: Validate parsed response
        result = _validate_analysis(parsed, question)

        # Step 7: Store in cache — enforce size limit
        if len(_query_cache) >= config.MAX_ANALYSIS_CACHE_SIZE:
            # Remove oldest entry when cache is full (FIFO by insertion order)
            oldest_key = next(iter(_query_cache))
            del _query_cache[oldest_key]
            print("[QueryAnalyzer] Cache full — removed oldest entry")
        _query_cache[normalized_q] = result

        return result

    except Exception as e:
        # Catch-all fallback — never crash the main pipeline
        print(f"[QueryAnalyzer] Unexpected error: {e} — fallback to SINGLE")
        return {"type": "SINGLE", "queries": [question]}
