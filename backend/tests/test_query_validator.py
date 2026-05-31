import pytest

from app.query_validator import QueryValidationError, is_dangerous_input, validate_sql


def test_union_all_analytics_allowed():
    sql = """
    SELECT region, SUM(amount) AS total FROM orders GROUP BY region
    UNION ALL
    SELECT region, SUM(amount) AS total FROM returns GROUP BY region
    """
    assert validate_sql(sql) == sql


def test_union_branch_must_be_select():
    sql = "SELECT 1 AS x UNION FROM DUAL"
    with pytest.raises(QueryValidationError, match="UNION branch 2"):
        validate_sql(sql)


def test_delete_still_forbidden():
    with pytest.raises(QueryValidationError, match="DELETE"):
        validate_sql("SELECT * FROM users WHERE DELETE = 0")


def test_updated_at_column_not_false_positive():
    validate_sql("SELECT updated_at FROM orders LIMIT 5")


def test_with_cte_select_allowed():
    sql = """
    WITH product_sales AS (
        SELECT product_id, SUM(quantity) AS qty FROM order_items GROUP BY product_id
    )
    SELECT SUM(qty) AS total FROM product_sales
    """
    assert validate_sql(sql) == sql


@pytest.mark.parametrize(
    "question",
    [
        "Explain the bar chart: Feb sales were 792,400 and Mar were 7,000 — what does that drop mean?",
        "Why did sales fall so much between Feb and Mar 2026?",
        "Can you clarify the chart above?",
        "What changed in customer behavior last quarter?",
        "Show me the sales drop by region",
    ],
)
def test_is_dangerous_input_allows_analytics_wording(question):
    assert is_dangerous_input(question) is False


@pytest.mark.parametrize(
    "question",
    [
        "drop table orders",
        "DELETE FROM customers WHERE id = 1",
        "please truncate table sales",
        "insert into users values (1, 'a')",
        "update orders set status = 'x' where id = 1",
        "alter table products add column x int",
        "remove all data from the database",
    ],
)
def test_is_dangerous_input_blocks_destructive_commands(question):
    assert is_dangerous_input(question) is True
