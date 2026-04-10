"""
execute_sql_tool.py
-------------------
Tool definition for executing a SQL SELECT query against the database.
Used natively by the Gemini model inside LangGraph.
"""

from langchain_core.tools import tool

from app.database import execute_query
from app.query_validator import validate_sql, QueryValidationError

@tool
def execute_sql_query(sql_query: str) -> str:
    """
    Executes a SQL SELECT query to retrieve data from the database.
    Use this to test your generated SQL against the actual database.
    
    Args:
        sql_query: The exact SQL string to execute.
    
    Returns:
        A stringified preview of the success results if execution succeeds,
        or a detailed error message describing what went wrong (e.g. invalid syntax, missing table).
    """
    try:
        # Step 1: Validate using guardrails (SELECT-only)
        valid_sql = validate_sql(sql_query)
        
        # Step 2: Run the query
        result = execute_query(valid_sql)
        
        if isinstance(result, dict) and "error" in result:
            # Query-level or DB-level failure
            return f"Error executing query: {result['error']}"
            
        # Return a short stringified preview so the LLM doesn't get flooded
        if not result:
            return "Success: Query returned 0 rows."
            
        # Preview first 5 rows
        preview = result[:5]
        return f"Success: Query returned {len(result)} rows. Preview of first 5 rows: {preview}"
        
    except QueryValidationError as e:
        return f"Validation Error: {e}"
    except Exception as e:
        return f"Unexpected Error: {e}"
