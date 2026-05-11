import json

# pyrefly: ignore [missing-import]
from langchain_core.messages import HumanMessage, ToolMessage

from app.agent_executor import _summarize_from_messages


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
