"""
database.py
-----------
Handles all database operations for the SQL Agent Demo.

Connects to TiDB Cloud (MySQL-compatible) using SSL and provides:
  - get_db_connection()    : Create and return a database connection
  - execute_query()        : Run a SQL query and return results
  - get_database_schema()  : Return a text description of the database schema
"""

# pyrefly: ignore [missing-import]
import mysql.connector
# pyrefly: ignore [missing-import]
from mysql.connector import Error

from app import config
from app.serialization import make_json_serializable


def select_sql_with_row_limit(inner_sql: str) -> str:
    """
    Wrap a validated single SELECT in an outer LIMIT so the engine returns at most
    MAX_RESULT_ROWS rows (TiDB / MySQL).
    """
    n = getattr(config, "MAX_RESULT_ROWS", 100)
    if n <= 0:
        return inner_sql.strip().rstrip(";")
    stripped = inner_sql.strip().rstrip(";")
    if not stripped:
        return inner_sql
    return f"SELECT * FROM (\n{stripped}\n) AS _agent_row_cap LIMIT {int(n)}"


# ---------------------------------------------------------------------------
# 1. get_db_connection
# ---------------------------------------------------------------------------

def get_db_connection():
    """
    Create and return a MySQL connection to TiDB Cloud.

    Reads all credentials from config.py (which loads them from .env).
    TiDB Cloud requires SSL — we pass the CA certificate path via ssl_config.

    Returns:
        mysql.connector.connection.MySQLConnection: An open database connection.

    Raises:
        Exception: If the connection cannot be established.
    """
    # SSL configuration — TiDB Cloud requires a CA certificate for secure connections.
    # ssl_config = {
    #     "ca": config.DB_CA_CERT  # Path to the CA cert downloaded from TiDB console
    # }

    try:
        connection = mysql.connector.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME,
            ssl_ca=config.DB_CA_CERT,
            ssl_verify_cert=True,
            ssl_verify_identity=True,
            use_pure=True,
            autocommit=True
        )
        return connection

    except Error as e:
        raise Exception(f"Database connection failed: {str(e)}")


# ---------------------------------------------------------------------------
# 2. execute_query
# ---------------------------------------------------------------------------

def execute_query(sql_query: str):
    """
    Execute a SQL query and return the results as a list of dictionaries.

    Each row in the result is a dict where keys are column names, e.g.:
        [{"name": "Rahul", "city": "Pune"}, {"name": "Sneha", "city": "Mumbai"}]

    If an error occurs, returns a dict with an "error" key:
        {"error": "error message here"}

    Args:
        sql_query (str): The SQL query to execute (e.g. "SELECT * FROM customers LIMIT 5").

    Returns:
        list[dict] | dict: Query results, or an error dictionary.
    """
    connection = None
    cursor = None

    try:
        # Step 1: Open a connection
        connection = get_db_connection()

        # Step 2: Create a cursor that returns rows as dictionaries
        cursor = connection.cursor(dictionary=True)

        # Step 3: Run the query (always capped at MAX_RESULT_ROWS)
        sql_exec = select_sql_with_row_limit(sql_query)
        cursor.execute(sql_exec)

        # Step 4: Fetch rows in chunks (avoids one huge fetchall buffer)
        results: list[dict] = []
        batch_size = 500
        while True:
            batch = cursor.fetchmany(batch_size)
            if not batch:
                break
            results.extend(batch)

        return results  # e.g. [{"column": "value", ...}, ...]

    except Exception as e:
        # Return a structured error response instead of crashing
        return {"error": str(e)}

    finally:
        # Always clean up — close cursor and connection even if an error occurred
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# ---------------------------------------------------------------------------
# 2b. iter_query_rows — chunked fetch for streaming responses
# ---------------------------------------------------------------------------


def iter_query_rows(sql_query: str, *, batch_size: int = 200):
    """
    Execute a SELECT and yield JSON-serializable row dicts using fetchmany batches.

    Yields:
        dict: One row at a time.

    Raises:
        Exception: On connection / SQL errors (same surface as execute_query failures).
    """
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        sql_exec = select_sql_with_row_limit(sql_query)
        cursor.execute(sql_exec)
        max_rows = getattr(config, "MAX_RESULT_ROWS", 100)
        yielded = 0
        while True:
            batch = cursor.fetchmany(batch_size)
            if not batch:
                break
            for row in batch:
                if max_rows > 0 and yielded >= max_rows:
                    return
                yield make_json_serializable(row)
                yielded += 1
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# ---------------------------------------------------------------------------
# 3. get_database_schema
# ---------------------------------------------------------------------------

def get_database_schema(*, force_refresh: bool = False) -> str:
    """
    Return a plain-text description of the database schema (TTL-cached).

    Uses ``schema_cache`` with periodic background refresh via ``schema_sync``.
    Set ``force_refresh=True`` to bypass TTL and read live from the database.
    """
    from app.schema_cache import get_cached_schema_text

    try:
        return get_cached_schema_text(force_refresh=force_refresh)
    except Exception as e:
        print(f"Warning: Failed to fetch dynamic schema: {e}")
        return "Schema unavailable. Database connection failed."
