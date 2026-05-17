from app.chart_inference import infer_chart_config, _should_skip_chart
from app.question_planner import build_question_plan


def test_customer_data_list_has_no_chart():
    schema = "Table: customers\nColumns: customer_id, first_name, last_name, email, phone, created_at"
    plan = build_question_plan("Give me data of customers", schema)
    assert "list_table" in plan["intents"]
    assert plan["needs_chart"] is False
    assert plan["chart_hint"] is None


def test_payment_breakdown_still_wants_chart():
    schema = "Table: payments\nColumns: payment_id, payment_method"
    plan = build_question_plan("payment method breakdown", schema)
    assert plan["chart_hint"] == "pie"


def test_tabular_customer_rows_skip_chart():
    rows = [
        {
            "customer_id": i,
            "first_name": f"User{i}",
            "last_name": "Test",
            "email": f"u{i}@test.com",
            "phone": "999",
            "created_at": "2025-01-01",
        }
        for i in range(1, 25)
    ]
    plan = {"needs_chart": True, "chart_hint": "pie", "intents": ["list_table"]}
    assert _should_skip_chart(plan, rows) is True
    assert infer_chart_config(plan, rows) is None
