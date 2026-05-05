from app.tools.sql_tools import _normalize_mysql_sql


def test_normalize_strftime_to_date_format():
    sql = "SELECT strftime('%Y-%m', order_date) AS month FROM orders"
    out = _normalize_mysql_sql(sql)
    assert "DATE_FORMAT(order_date, '%Y-%m')" in out
    assert "strftime" not in out.lower()


def test_normalize_order_date_filter_with_order_items():
    sql = (
        "SELECT SUM(price_at_purchase * quantity) AS total_sales "
        "FROM order_items WHERE MONTH(order_date) BETWEEN 1 AND 2"
    )
    out = _normalize_mysql_sql(sql)
    assert "JOIN orders o ON oi.order_id = o.order_id" in out
    assert "MONTH(o.order_date)" in out
