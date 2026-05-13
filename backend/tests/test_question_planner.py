from app.question_planner import build_question_plan


def test_planner_detects_operational_alert_strategy():
    plan = build_question_plan(
        "Which products are frequently ordered but have low stock in warehouses?",
        schema="Table: products\nTable: order_items\nTable: warehouse_inventory",
    )
    assert plan["strategy"] == "deterministic_sql"
    assert "operational_alert" in plan["intents"]
    assert plan["deterministic_sql"]


def test_planner_detects_strategic_recommendation():
    plan = build_question_plan(
        "How can we increase sales next quarter?",
        schema="Table: orders\nTable: order_items\nTable: products",
    )
    assert plan["strategy"] == "strategic_mode"
    assert "strategic_recommendation" in plan["intents"]


def test_revenue_by_category_requests_bar_chart():
    plan = build_question_plan(
        "Give me revenue by category",
        schema="Table: categories\nTable: products",
    )
    assert plan["needs_chart"] is True
    assert plan["chart_hint"] == "bar"


def test_sales_by_product_requests_bar_chart():
    plan = build_question_plan(
        "total sales by product",
        schema="Table: products",
    )
    assert plan["chart_hint"] == "bar"
