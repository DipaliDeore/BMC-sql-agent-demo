"""
query_validator.py - SQL Safety Layer (Module 4)
-------------------------------------------------
Validates AI-generated SQL queries before they are executed on the database.

Purpose:
    - Prevent destructive queries (DELETE, DROP, etc.)
    - Block SQL injection attempts
    - Ensure only safe SELECT queries reach the database
"""


# ── Custom Exception ──────────────────────────────────────────────────────────

class QueryValidationError(Exception):
    """Raised when a SQL query fails validation checks."""
    pass


# ── SQL Validation Function ───────────────────────────────────────────────────

def validate_sql(sql_query: str) -> str:
    """
    Validate a SQL query for safety before executing it.

    Checks performed:
        1. Query must not be empty
        2. Query must start with SELECT
        3. Query must not contain forbidden keywords
        4. Query must not contain SQL injection patterns

    Args:
        sql_query (str): The SQL query string to validate.

    Returns:
        str: The original sql_query if all checks pass.

    Raises:
        QueryValidationError: If the query fails any safety check.
    """

    # ── Check 1: Empty Query ──────────────────────────────────────────────
    # If the AI returned an empty or whitespace-only string, reject it.
    if not sql_query or not sql_query.strip():
        raise QueryValidationError("SQL query cannot be empty.")

    # ── Check 2: SELECT Only ─────────────────────────────────────────────
    # We only allow read-only SELECT queries.
    # Strip whitespace and check if the query starts with SELECT.
    upper_query = sql_query.strip().upper()

    if not upper_query.startswith("SELECT"):
        raise QueryValidationError(
            "Only SELECT queries are allowed. Data modification queries are not permitted."
        )

    # ── Check 3: Forbidden Keywords ──────────────────────────────────────
    # Even if the query starts with SELECT, it might contain dangerous
    # keywords like DELETE or DROP hidden inside (e.g., subqueries).
    # We check for each forbidden keyword (case-insensitive).
    forbidden_keywords = [
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
        "UNION",
        "SLEEP",
    ]

    for keyword in forbidden_keywords:
        # Convert both to uppercase for case-insensitive comparison
        if keyword in upper_query:
            raise QueryValidationError(
                f"Query contains forbidden keyword: {keyword}. Only read-only queries are allowed."
            )

    # ── Check 4: SQL Injection Patterns ──────────────────────────────────
    # Block common SQL injection techniques:
    #   --      : Single-line comment (can hide malicious code after it)
    #   #       : MySQL single-line comment
    #   ; + word: Multiple statements (e.g., "; DROP TABLE")
    #   /*      : Block comment open (can obfuscate malicious SQL)
    #   */      : Block comment close
    #   xp_     : Extended stored procedures (SQL Server attack vector)
    unsafe_patterns = ["--", "#", "/*", "*/", "xp_"]

    for pattern in unsafe_patterns:
        if pattern in sql_query:
            raise QueryValidationError(
                "Query contains potentially unsafe pattern."
            )

    # Check for multiple statements: semicolon followed by another word
    # This catches things like: "SELECT * FROM users; DROP TABLE users"
    stripped = sql_query.strip()
    semicolon_pos = stripped.find(";")

    if semicolon_pos != -1:
        # Check if there is any non-whitespace text after the semicolon
        after_semicolon = stripped[semicolon_pos + 1:].strip()
        if after_semicolon:
            raise QueryValidationError(
                "Query contains potentially unsafe pattern."
            )

    # ── All checks passed ────────────────────────────────────────────────
    # Return the original query unchanged.
    return sql_query
