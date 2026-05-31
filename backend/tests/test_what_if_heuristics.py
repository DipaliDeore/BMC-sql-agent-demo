"""Parametrized tests for what-if heuristic SQL planners."""

import pytest

from app.what_if_heuristics import build_heuristic_plan

SCHEMA_FULL = """
Table: order_items — product_id, price_at_purchase, quantity, order_id
Table: orders — order_id, customer_id
Table: customers — customer_id
Table: products — product_id
Table: refunds — refund_id, refund_amount, order_id
Table: returns — return_id, order_id
Table: shipping — shipped_date, delivery_date
Table: seller_products — seller_id, product_id
Table: payments — amount, payment_status
"""


@pytest.mark.parametrize(
    "question,expected_fragment",
    [
        ("What if total sales increase by 10%?", "baseline_total_sales"),
        ("What if product prices increase by 5%?", "baseline_total_sales"),
        ("What if we give a 10% discount on all products?", "baseline_total_sales"),
        (
            "What if high-selling products increase their sales by 20%?",
            "baseline_total_sales",
        ),
        ("What if we stop selling low-performing products?", "baseline_total_sales"),
        (
            "What if we promote top 5 products and sales double?",
            "baseline_total_sales",
        ),
        (
            "What if we reduce prices for slow-moving products by 15%?",
            "baseline_total_sales",
        ),
        ("What if repeat customers increase by 20%?", "baseline_total_sales"),
        (
            "What if we convert 10% of one-time buyers into repeat customers?",
            "baseline_total_sales",
        ),
        ("What if high-value customers spend 15% more?", "baseline_total_sales"),
        ("What if we reduce returns by 30%?", "baseline_refund_total"),
        ("What if refund amounts decrease by 20%?", "baseline_refund_total"),
        (
            "What if we fix defective products and eliminate returns?",
            "baseline_refund_total",
        ),
        (
            "What if we always match the lowest competitor price?",
            "baseline_total_sales",
        ),
        (
            "What if we increase prices but reduce returns?",
            "baseline_net_revenue",
        ),
        ("What if best sellers reduce price by 5%?", "baseline_total_sales"),
        (
            "What if delivery time improves by 2 days?",
            "baseline_avg_delivery_days",
        ),
        (
            "What if faster delivery increases sales by 15%?",
            "baseline_total_sales",
        ),
    ],
)
def test_heuristic_plan_for_user_scenarios(question, expected_fragment):
    plan = build_heuristic_plan(question, SCHEMA_FULL)
    assert plan is not None, f"No plan for: {question}"
    assert expected_fragment in plan["queries"][0]
    assert plan["baseline_column"]
    assert plan["scenario_column"]
