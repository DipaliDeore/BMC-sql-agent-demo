from app.question_planner import build_question_plan
from app.trend_pipeline import should_use_trend_pipeline


def test_refund_trend_uses_trend_pipeline():
    schema = "Table: returns\nColumns: return_id, refund_amount, return_date"
    plan = build_question_plan("what is the refund amount trend over time", schema)
    assert plan["chart_hint"] == "line"
    assert should_use_trend_pipeline("what is the refund amount trend over time", plan)


def test_strategic_question_not_trend_pipeline():
    schema = "Table: returns\nTable: products"
    plan = build_question_plan("How can I reduce product returns?", schema)
    assert not should_use_trend_pipeline("How can I reduce product returns?", plan)
