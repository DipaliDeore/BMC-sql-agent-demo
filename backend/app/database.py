"""
database.py
-----------
Handles all database operations for the SQL Agent Demo.

Connects to TiDB Cloud (MySQL-compatible) using SSL and provides:
  - get_db_connection()    : Create and return a database connection
  - execute_query()        : Run a SQL query and return results
  - get_database_schema()  : Return a text description of the database schema
"""

import mysql.connector
from mysql.connector import Error
from app import config


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

        # Step 3: Run the query
        cursor.execute(sql_query)

        # Step 4: Fetch all rows
        results = cursor.fetchall()

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
# 3. get_database_schema
# ---------------------------------------------------------------------------

def get_database_schema() -> str:
    """
    Return a plain-text description of the database schema.
    
    This schema is dynamically fetched from the database, including tables,
    columns, and foreign key relationships.

    Returns:
        str: A formatted string describing all tables, columns, and relationships.
    """
    connection = None
    cursor = None
    schema_lines = []

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        # 1. Fetch tables
        cursor.execute("SHOW TABLES")
        tables = [list(row.values())[0] for row in cursor.fetchall()]
        
        # 2. Fetch columns for each table
        for table in tables:
            cursor.execute(f"DESCRIBE `{table}`")
            columns = [row['Field'] for row in cursor.fetchall()]
            schema_lines.append(f"Table: {table}")
            schema_lines.append(f"Columns: {', '.join(columns)}\n")
            
        # 3. Fetch foreign key relationships
        cursor.execute("""
            SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME 
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE 
            WHERE REFERENCED_TABLE_SCHEMA = %s AND REFERENCED_TABLE_NAME IS NOT NULL
        """, (config.DB_NAME,))
        fks = cursor.fetchall()
        
        if fks:
            schema_lines.append("Relationships:")
            for fk in fks:
                schema_lines.append(
                    f"{fk['TABLE_NAME']}.{fk['COLUMN_NAME']} \u2192 {fk['REFERENCED_TABLE_NAME']}.{fk['REFERENCED_COLUMN_NAME']}"
                )
                
        return "\n".join(schema_lines).strip()
        
    except Exception as e:
        print(f"Warning: Failed to fetch dynamic schema: {e}")
        # Fallback to generic message or fail gracefully if the database isn't working
        return "Schema unavailable. Database connection failed."
        
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
