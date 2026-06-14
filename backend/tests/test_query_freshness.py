"""Tests for live-metric / revenue freshness helpers."""

from app.query_freshness import (
    cached_sql_safe_for_replay,
    is_open_total_revenue_question,
    needs_fresh_metric_query,
)
from app.question_planner import build_question_plan


def test_open_total_revenue_detected():
    assert is_open_total_revenue_question("What is total revenue?")
    assert is_open_total_revenue_question("tell me total revenue")
    assert not is_open_total_revenue_question("total revenue in 2025")


def test_planner_uses_payments_for_total_revenue():
    schema = "Table: payments (amount)\nTable: order_items (quantity, price_at_purchase)"
    plan = build_question_plan("What is total revenue?", schema)
    assert plan["strategy"] == "deterministic_sql"
    assert "SUM(amount)" in plan["deterministic_sql"][0]
    assert "payments" in plan["deterministic_sql"][0]


def test_cached_order_items_sql_rejected_for_total_revenue():
    sql = "SELECT SUM(quantity * price_at_purchase) AS total FROM order_items"
    assert cached_sql_safe_for_replay("What is total revenue?", sql) is False


def test_cached_payments_sql_allowed_for_total_revenue():
    sql = "SELECT SUM(amount) AS total_revenue FROM payments"
    assert cached_sql_safe_for_replay("What is total revenue?", sql) is True


def test_needs_fresh_metric_for_total_revenue():
    assert needs_fresh_metric_query("What is total revenue?")


def test_live_database_query_for_list_questions():
    from app.query_freshness import needs_live_database_query

    assert needs_live_database_query("Show me all customers", {"intents": ["list_table"]})
    assert not needs_live_database_query("Explain that chart above")


def test_explain_prior_not_live():
    from app.query_freshness import needs_live_database_query

    assert needs_live_database_query("Explain the chart above") is False
