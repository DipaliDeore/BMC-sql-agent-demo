"""Tests for what-if scenario pipeline routing and helpers."""

from app.question_planner import build_question_plan
from app.what_if_heuristics import build_heuristic_plan
from app.what_if_pipeline import (
    _pick_baseline_scenario_cols,
    _what_if_explanation,
    should_use_what_if_pipeline,
)


def test_planner_detects_what_if_intent():
    plan = build_question_plan(
        "What if sales increased by 10%?",
        schema="Table: orders\nColumns: order_id, total_amount",
    )
    assert "what_if_scenario" in plan["intents"]
    assert plan["strategy"] == "what_if_mode"


def test_should_use_what_if_for_percent_scenario():
    plan = build_question_plan(
        "What if sales increased by 10%?",
        schema="Table: orders",
    )
    assert should_use_what_if_pipeline("What if sales increased by 10%?", plan)


def test_should_not_use_what_if_for_pure_advisory():
    plan = build_question_plan(
        "How can I increase sales?",
        schema="Table: orders",
    )
    assert not should_use_what_if_pipeline("How can I increase sales?", plan)


def test_pick_baseline_scenario_columns():
    row = {"baseline_sales": 1000, "scenario_sales": 1100}
    pair = _pick_baseline_scenario_cols(row, "baseline_sales", "scenario_sales")
    assert pair == ("baseline_sales", "scenario_sales")


def test_heuristic_top5_products_double():
    schema = "Table: order_items\nColumns: product_id, price_at_purchase, quantity\nTable: products"
    plan = build_heuristic_plan(
        "What if we promote top 5 products and sales double?",
        schema,
    )
    assert plan is not None
    assert "baseline_total_sales" in plan["queries"][0]
    assert "scenario_total_sales" in plan["queries"][0]
    assert plan["baseline_column"] == "baseline_total_sales"


def test_execute_what_if_uses_heuristic_without_llm(monkeypatch):
    schema = "Table: order_items\nColumns: product_id, price_at_purchase, quantity\nTable: products"
    plan = {
        "queries": [
            "SELECT 100 AS baseline_total_sales, 150 AS scenario_total_sales"
        ],
        "scenario_summary": "top 5 product sales ×2",
        "baseline_column": "baseline_total_sales",
        "scenario_column": "scenario_total_sales",
    }
    monkeypatch.setattr("app.what_if_pipeline.build_heuristic_plan", lambda q, s: plan)
    monkeypatch.setattr(
        "app.what_if_pipeline._plan_what_if_sql",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM should not run")),
    )
    monkeypatch.setattr(
        "app.what_if_pipeline._execute_safe_sql",
        lambda sql: {
            "success": True,
            "results": [{"baseline_total_sales": 100, "scenario_total_sales": 150}],
            "sql": sql,
        },
    )
    from app.what_if_pipeline import execute_what_if_pipeline

    out = execute_what_if_pipeline(
        "What if we promote top 5 products and sales double?",
        schema,
    )
    assert out is not None
    assert out["response_kind"] == "what_if_analysis"
    assert out["row_count"] == 2


def test_what_if_explanation_includes_delta():
    text = _what_if_explanation(
        "What if sales increased by 10%?",
        {"baseline_sales": 1000, "scenario_sales": 1100},
        baseline_key="baseline_sales",
        scenario_key="scenario_sales",
        scenario_summary="10% increase in sales",
    )
    assert "1,100" in text or "1100" in text
    assert "simulation" in text.lower() or "read-only" in text.lower()
