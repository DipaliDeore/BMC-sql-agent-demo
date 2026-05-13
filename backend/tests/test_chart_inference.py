from app.chart_inference import apply_inferred_chart_from_plan, infer_chart_config
from app.question_planner import build_question_plan


def test_infer_bar_revenue_by_category_shape():
    plan = build_question_plan("revenue by category", schema="Table: categories")
    rows = [
        {"category_name": "A", "total_revenue": 100},
        {"category_name": "B", "total_revenue": 200},
    ]
    cfg = infer_chart_config(plan, rows)
    assert cfg is not None
    assert cfg["chart_type"] == "bar"
    assert cfg["x_column"] == "category_name"
    assert cfg["y_column"] == "total_revenue"


def test_apply_fills_missing_chart_on_summary():
    plan = build_question_plan("revenue by category", schema="Table: categories")
    summary = {
        "status": "success",
        "is_multi": False,
        "chart_config": None,
        "results": [{"category_name": "X", "total_revenue": 1}],
        "row_count": 1,
    }
    apply_inferred_chart_from_plan(summary, plan)
    assert summary["chart_config"] is not None
    assert summary["chart_config"]["chart_type"] == "bar"


def test_apply_does_not_override_existing_chart():
    plan = build_question_plan("revenue by category", schema="Table: categories")
    existing = {"chart_type": "pie", "x_column": "a", "y_column": "b", "is_pie_chart": True}
    summary = {
        "status": "success",
        "is_multi": False,
        "chart_config": existing,
        "results": [{"category_name": "X", "total_revenue": 1}],
    }
    apply_inferred_chart_from_plan(summary, plan)
    assert summary["chart_config"] == existing


def test_infer_line_dual_series():
    plan = build_question_plan(
        "daily trend successful vs failed payments",
        schema="Table: payments",
    )
    assert plan["chart_hint"] == "line"
    rows = [
        {
            "payment_date": "2026-02-01",
            "successful_payments": 3,
            "failed_payments": 1,
        },
    ]
    cfg = infer_chart_config(plan, rows)
    assert cfg is not None
    assert cfg["chart_type"] == "line"
    assert cfg["x_column"] == "payment_date"
    assert set([cfg["y_column"], cfg.get("y_column_2")]) == {"successful_payments", "failed_payments"}
