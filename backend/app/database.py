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

    This schema is passed to the AI (Gemini) so it understands the table
    structure and can generate accurate SQL queries.

    Returns:
        str: A formatted string describing all tables, columns, and relationships.
    """
    schema = """
Table: customers
Columns: customer_id, name, email, city, created_at

Table: products
Columns: product_id, product_name, category, price

Table: orders
Columns: order_id, customer_id, order_date, total_amount, order_status

Table: order_items
Columns: order_item_id, order_id, product_id, quantity

Relationships:
customers.customer_id → orders.customer_id
orders.order_id       → order_items.order_id
products.product_id   → order_items.product_id
""".strip()

    return schema
