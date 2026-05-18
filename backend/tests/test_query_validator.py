import pytest

from app.query_validator import QueryValidationError, validate_sql


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
