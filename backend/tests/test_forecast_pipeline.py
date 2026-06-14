"""Tests for forecast_pipeline — routing, horizon parsing, and model path."""

from unittest.mock import patch

from app.forecast_pipeline import (
    FORECAST_RESPONSE_KIND,
    _forecast_explanation,
    _months_to_target_quarter,
    _run_forecast,
    parse_forecast_horizon,
    parse_target_quarter,
    should_use_forecast_pipeline,
)
from app.question_planner import build_question_plan


def test_should_use_forecast_pipeline_predict_sales():
    schema = "orders order_date amount"
    plan = build_question_plan("Predict next 3 months sales", schema)
    assert "forecast" in plan["intents"]
    assert should_use_forecast_pipeline("Predict next 3 months sales", plan)


def test_should_use_forecast_pipeline_estimate_q4_2027():
    schema = "orders order_date total_amount"
    question = "Estimate sales for Q4 2027"
    plan = build_question_plan(question, schema)
    assert "forecast" in plan["intents"]
    assert should_use_forecast_pipeline(question, plan)


def test_parse_target_quarter_q4_2027():
    assert parse_target_quarter("Estimate sales for Q4 2027") == (2027, 4)


def test_parse_horizon_specific_quarter_with_history():
    from datetime import datetime

    last_dt = datetime(2025, 6, 1)
    horizon, period = parse_forecast_horizon(
        "Estimate sales for Q4 2027", last_historical_dt=last_dt
    )
    assert period == "month"
    assert horizon == _months_to_target_quarter(last_dt, 2027, 4)


def test_parse_horizon_next_month():
    assert parse_forecast_horizon("What will revenue be next month?") == (1, "month")


def test_parse_horizon_next_year():
    assert parse_forecast_horizon("Expected annual revenue for next year") == (12, "month")


def test_parse_horizon_in_6_months():
    assert parse_forecast_horizon("What will revenue be in 6 months?") == (6, "month")


def test_should_not_use_forecast_for_plain_trend():
    schema = "orders order_date"
    plan = build_question_plan("What is the sales trend over time by month", schema)
    assert should_use_forecast_pipeline("What is the sales trend over time by month", plan) is False


def test_parse_horizon_next_3_months():
    assert parse_forecast_horizon("Predict next 3 months sales") == (3, "month")


def test_parse_horizon_next_quarter():
    assert parse_forecast_horizon("Forecast revenue for the next quarter") == (3, "month")


def test_parse_horizon_next_6_weeks():
    assert parse_forecast_horizon("Predict the next 6 weeks of orders") == (6, "week")


def test_parse_horizon_default():
    assert parse_forecast_horizon("Forecast sales") == (3, "month")


def test_insufficient_history_message():
    rows = [{"month": "2024-01", "total_sales": 100}]
    result = _run_forecast(rows, horizon=3, period="month")
    assert result["ok"] is False
    assert "at least 3" in result["message"].lower()


def test_linear_forecast_with_synthetic_monthly_rows():
    rows = [
        {"month": f"2024-{m:02d}", "total_sales": 1000 + m * 50}
        for m in range(1, 9)
    ]
    with patch("app.forecast_pipeline._arima_forecast", return_value=None):
        result = _run_forecast(rows, horizon=3, period="month")

    assert result["ok"] is True
    assert result["method"] == "linear_trend"
    assert result["history_points"] == 8
    combined = result["rows"]
    assert len(combined) == 11  # 8 actual + 3 forecast
    assert sum(1 for r in combined if r.get("is_forecast")) == 3
    assert combined[0]["series"] == "actual"
    assert combined[-1]["series"] == "forecast"
    assert combined[-1].get("is_forecast") is True


def test_arima_forecast_with_mock():
    rows = [
        {"month": f"2024-{m:02d}", "total_sales": 1000 + m * 80}
        for m in range(1, 13)
    ]
    with patch("app.forecast_pipeline._arima_forecast", return_value=[1500.0, 1600.0, 1700.0]):
        result = _run_forecast(rows, horizon=3, period="month")

    assert result["ok"] is True
    assert result["method"] == "arima"
    forecast_rows = [r for r in result["rows"] if r.get("is_forecast")]
    assert len(forecast_rows) == 3
    fc_col = result["forecast_col"]
    assert forecast_rows[0][fc_col] == 1500.0


def test_forecast_explanation_includes_caveat():
    result = {
        "ok": True,
        "method": "arima",
        "horizon": 3,
        "period": "month",
        "history_points": 12,
        "metric_key": "total_sales",
        "forecast_col": "total_sales_forecast",
        "rows": [
            {"month": "2024-12", "total_sales": 1200, "is_forecast": False},
            {"month": "2025-01", "total_sales_forecast": 1300, "is_forecast": True},
        ],
    }
    text = _forecast_explanation("Predict next 3 months sales", result)
    assert "ARIMA" in text
    assert "statistical" in text.lower() or "guarantee" in text.lower()


def test_forecast_response_kind_constant():
    assert FORECAST_RESPONSE_KIND == "forecast_series"
