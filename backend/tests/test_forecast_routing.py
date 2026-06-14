"""Parametrized routing tests for demo forecast / what-if / strategic questions."""

import pytest

from app.forecast_pipeline import should_use_forecast_pipeline
from app.question_planner import build_question_plan
from app.strategic_pipeline import should_use_strategic_pipeline
from app.what_if_pipeline import should_use_what_if_pipeline

SCHEMA = """Table: orders (order_id, customer_id, order_date, total_amount, order_status)
Table: order_items (order_item_id, order_id, product_id, quantity, price_at_purchase)
Table: payments (payment_id, order_id, amount, payment_date, payment_status)
Table: products (product_id, name, category_id)
Table: customers (customer_id, name, email)
Table: warehouse_inventory (product_id, warehouse_id, stock)
Table: returns (return_id, order_id, product_id, return_date)
Table: refunds (refund_id, order_id, refund_amount, refund_date)"""


def _route(question: str) -> str:
    plan = build_question_plan(question, SCHEMA)
    if plan.get("strategy") == "deterministic_sql":
        return "DETERMINISTIC"
    if should_use_forecast_pipeline(question, plan):
        return "FORECAST"
    if should_use_what_if_pipeline(question, plan):
        return "WHAT_IF"
    if should_use_strategic_pipeline(question, plan):
        return "STRATEGIC"
    return "GENERIC"


@pytest.mark.parametrize(
    "question,expected",
    [
        ("What will my revenue be next month based on historical trends?", "FORECAST"),
        ("Predict revenue for the next 3 months.", "FORECAST"),
        ("Estimate sales for Q4 2027.", "FORECAST"),
        ("What is the expected annual revenue for next year?", "FORECAST"),
        ("Show projected monthly revenue for the next 12 months.", "FORECAST"),
        (
            "If revenue continues growing at the current rate, what will revenue be in 6 months?",
            "FORECAST",
        ),
        ("Predict customer growth for the next 6 months.", "FORECAST"),
        ("Predict the number of returns next month.", "FORECAST"),
        ("Estimate refund costs for the next quarter.", "FORECAST"),
        ("Predict demand for each product category.", "FORECAST"),
        (
            "What will revenue look like if sales increase by 15% every month?",
            "WHAT_IF",
        ),
        (
            "How much revenue can we expect if order volume grows by 20%?",
            "WHAT_IF",
        ),
        ("What happens if average order value increases by 10%?", "WHAT_IF"),
        (
            "What will revenue be next year if sales increase by 10% every quarter?",
            "WHAT_IF",
        ),
        ("What if returns decrease by 25%? How will profit change?", "WHAT_IF"),
        (
            "Which products are likely to run out of stock next month?",
            "STRATEGIC",
        ),
        (
            "Which customers are likely to become repeat buyers?",
            "STRATEGIC",
        ),
        (
            "What should I do to increase revenue by 20% next quarter?",
            "STRATEGIC",
        ),
        (
            "Which products are expected to be top sellers next month?",
            "GENERIC",
        ),
    ],
)
def test_demo_question_routing(question, expected):
    assert _route(question) == expected
