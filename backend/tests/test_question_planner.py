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
