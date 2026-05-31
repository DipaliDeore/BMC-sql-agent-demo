"""
query_validator.py - SQL Safety Layer (Module 4)
-------------------------------------------------
Validates AI-generated SQL queries before they are executed on the database.

Purpose:
    - Prevent destructive queries (DELETE, DROP, etc.)
    - Block SQL injection attempts
    - Ensure only safe SELECT queries reach the database
"""

import re


# ── Custom Exception ──────────────────────────────────────────────────────────

class QueryValidationError(Exception):
    """Raised when a SQL query fails validation checks."""
    pass


# Whole-word matches only (avoids false positives like column `updated_at`).
_FORBIDDEN_KEYWORDS = (
    "DELETE",
    "UPDATE",
    "INSERT",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "EXEC",
    "EXECUTE",
    "GRANT",
    "REVOKE",
    "SLEEP",
    # UNION is allowed for legitimate analytics (e.g. combined SELECT branches).
)


def _contains_keyword(sql_upper: str, keyword: str) -> bool:
    return bool(re.search(rf"\b{re.escape(keyword)}\b", sql_upper))


def _split_union_branches(sql: str) -> list[str]:
    """Split on top-level UNION / UNION ALL (case-insensitive)."""
    parts = re.split(r"\bUNION\s+ALL\b|\bUNION\b", sql, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


def _validate_union_branches(sql: str) -> None:
    """Each UNION branch must be a SELECT (analytics use case)."""
    branches = _split_union_branches(sql)
    if len(branches) <= 1:
        return
    for i, branch in enumerate(branches, start=1):
        if not branch.upper().lstrip().startswith("SELECT"):
            raise QueryValidationError(
                f"UNION branch {i} must be a SELECT query. Only read-only queries are allowed."
            )
        for keyword in _FORBIDDEN_KEYWORDS:
            if _contains_keyword(branch.upper(), keyword):
                raise QueryValidationError(
                    f"UNION branch {i} contains forbidden keyword: {keyword}. "
                    "Only read-only queries are allowed."
                )


# ── SQL Validation Function ───────────────────────────────────────────────────

def validate_sql(sql_query: str) -> str:
    """
    Validate a SQL query for safety before executing it.

    Checks performed:
        1. Query must not be empty
        2. Query must start with SELECT
        3. Query must not contain forbidden keywords (whole-word)
        4. Query must not contain SQL injection patterns

    Args:
        sql_query (str): The SQL query string to validate.

    Returns:
        str: The original sql_query if all checks pass.

    Raises:
        QueryValidationError: If the query fails any safety check.
    """

    # ── Check 1: Empty Query ──────────────────────────────────────────────
    if not sql_query or not sql_query.strip():
        raise QueryValidationError("SQL query cannot be empty.")

    # ── Check 2: SELECT (or WITH … SELECT) only ─────────────────────────────
    upper_query = sql_query.strip().upper()

    is_select = upper_query.startswith("SELECT")
    is_cte = upper_query.startswith("WITH") and bool(
        re.search(r"\bSELECT\b", upper_query)
    )
    if not is_select and not is_cte:
        raise QueryValidationError(
            "Only SELECT queries are allowed. Data modification queries are not permitted."
        )

    # ── Check 3: Forbidden Keywords ──────────────────────────────────────
    for keyword in _FORBIDDEN_KEYWORDS:
        if _contains_keyword(upper_query, keyword):
            raise QueryValidationError(
                f"Query contains forbidden keyword: {keyword}. Only read-only queries are allowed."
            )

    _validate_union_branches(sql_query)

    # ── Check 4: SQL Injection Patterns ──────────────────────────────────
    unsafe_patterns = ["--", "#", "/*", "*/", "xp_"]

    for pattern in unsafe_patterns:
        if pattern in sql_query:
            raise QueryValidationError(
                "Query contains potentially unsafe pattern."
            )

    stripped = sql_query.strip()
    semicolon_pos = stripped.find(";")

    if semicolon_pos != -1:
        after_semicolon = stripped[semicolon_pos + 1:].strip()
        if after_semicolon:
            raise QueryValidationError(
                "Query contains potentially unsafe pattern."
            )

    return sql_query


# Natural-language destructive intent (command-like), not bare substrings.
# Avoids false positives: "sales drop", "clarify", "what changed", etc.
_DANGEROUS_NL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bdelete\s+(from|all|every|rows?|records?|data)\b", re.I),
    re.compile(r"\bdelete\s+(the\s+)?(table|rows?|records?|data)\b", re.I),
    re.compile(r"\bdrop\s+(table|database|index|view|schema|column)\b", re.I),
    re.compile(r"\btruncate\s+(table|all)?\b", re.I),
    re.compile(r"\binsert\s+into\b", re.I),
    re.compile(r"\bupdate\s+[`\w.]+\s+set\b", re.I),
    re.compile(r"\balter\s+table\b", re.I),
    re.compile(r"\b(remove|erase|wipe|destroy)\s+(all|rows?|records?|data|from)\b", re.I),
    re.compile(r"\b(modify|edit)\s+(the\s+)?(data|table|records?|database)\b", re.I),
    re.compile(r"\bchange\s+(the\s+)?(data|table|records?|database|values)\b", re.I),
    re.compile(r"\bclear\s+(the\s+)?(table|data|database|records?)\b", re.I),
)


def is_dangerous_input(question: str) -> bool:
    """
    Detect destructive *intent* in a natural-language question.

    Uses command-like phrases (e.g. ``drop table``, ``delete from``), not
    substring matches, so analytics wording like "sales drop" is allowed.
    """
    text = (question or "").strip()
    if not text:
        return False
    return any(p.search(text) for p in _DANGEROUS_NL_PATTERNS)
