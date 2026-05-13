import json

# pyrefly: ignore [missing-import]
from langchain_core.messages import HumanMessage, ToolMessage

from app.agent_executor import _summarize_from_messages, apply_strategic_response_shape


def test_partial_failure_keeps_successful_parts():
    messages = [
        HumanMessage(content="Give me total sales and jan-feb sales"),
        ToolMessage(
            content=json.dumps(
                {
                "success": True,
                "sql": "SELECT SUM(price_at_purchase * quantity) AS total_sales FROM order_items",
                "results": [{"total_sales": 799400}],
                }
            ),
            tool_call_id="1",
        ),
        ToolMessage(
            content=json.dumps(
                {
                "success": False,
                "sql": "SELECT ...",
                "error": "Unknown column 'order_date' in 'where clause'",
                "error_type": "SQL_ERROR",
                }
            ),
            tool_call_id="2",
        ),
    ]
    out = _summarize_from_messages(messages)
    assert out["status"] == "success"
    assert out["is_multi"] is True
    assert len(out["sub_responses"]) == 2
    assert any(s["status"] == "success" for s in out["sub_responses"])
    assert any("could not run this part" in s["explanation"].lower() for s in out["sub_responses"])


def test_chart_binds_to_most_recent_matching_sql():
    """Same x/y column names on two runs: render_chart attaches to the later (corrected) result."""
    messages = [
        HumanMessage(content="payments by day"),
        ToolMessage(
            content=json.dumps(
                {
                    "success": True,
                    "sql": "SELECT ... wrong status ...",
                    "results": [
                        {"payment_date": "2026-02-01", "successful_payments": 0, "failed_payments": 0},
                    ],
                }
            ),
            tool_call_id="1",
        ),
        ToolMessage(
            content=json.dumps(
                {
                    "success": True,
                    "sql": "SELECT ... correct status ...",
                    "results": [
                        {"payment_date": "2026-02-01", "successful_payments": 3, "failed_payments": 1},
                    ],
                }
            ),
            tool_call_id="2",
        ),
        ToolMessage(
            content=json.dumps(
                {
                    "success": True,
                    "chart_type": "line",
                    "x_column": "payment_date",
                    "y_column": "successful_payments",
                    "y_column_2": "failed_payments",
                }
            ),
            tool_call_id="3",
        ),
    ]
    out = _summarize_from_messages(messages)
    assert out["is_multi"] is True
    subs = out["sub_responses"]
    assert subs[0]["chart_config"] is None
    assert subs[1]["chart_config"] is not None
    assert subs[1]["chart_config"]["chart_type"] == "line"
    assert subs[1]["chart_config"]["y_column_2"] == "failed_payments"


def test_strategic_mode_collapses_multi_subresponses():
    summary = {
        "status": "success",
        "is_multi": True,
        "explanation": "To improve sales, focus on high-value products and loyalty.",
        "sub_responses": [
            {
                "question": "Result 1",
                "explanation": "Here is the total quantity sold breakdown by product name:",
                "results": [{"product_name": "Nike T-Shirt", "total_quantity_sold": 5}],
                "sql": "SELECT 1",
            },
            {
                "question": "Result 2",
                "explanation": "Here is the total revenue breakdown by product name:",
                "results": [{"product_name": "iPhone 14", "total_revenue": 140000}],
                "sql": "SELECT 2",
            },
        ],
        "results": [],
        "row_count": 0,
        "sql_query": "",
        "chart_config": None,
    }

    apply_strategic_response_shape(summary, {"strategy": "strategic_mode"})

    assert summary["is_multi"] is False
    assert summary["sub_responses"] == []
    assert summary["results"] == []
    assert summary["sql_query"] == ""
    assert "To improve sales" in summary["explanation"]
