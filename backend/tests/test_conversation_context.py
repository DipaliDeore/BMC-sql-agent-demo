from app.conversation_context import (
    build_context_from_messages,
    format_message_for_context,
)


def test_format_assistant_with_chart_and_results():
    msg = {
        "role": "assistant",
        "content": "I queried your connected database to answer this chart.",
        "payload": {
            "sql": "SELECT month, SUM(sales) AS total_sales FROM orders GROUP BY month",
            "response_kind": "image_db_grounded",
            "chart_config": {
                "chart_type": "bar",
                "x_column": "sales_month",
                "y_column": "total_sales",
            },
            "row_count": 2,
            "results": [
                {"sales_month": "2026-02", "total_sales": 792400},
                {"sales_month": "2026-03", "total_sales": 7000},
            ],
        },
    }
    text = format_message_for_context(msg)
    assert "2026-02" in text
    assert "792400" in text
    assert "image_db_grounded" in text
    assert "Chart shown in UI" in text
    assert "sales_month" in text


def test_build_context_excludes_trailing_user():
    messages = [
        {"role": "user", "content": "[Image attachment]", "payload": None},
        {
            "role": "assistant",
            "content": "Feb vs Mar sales.",
            "payload": {
                "sql": "SELECT 1",
                "results": [{"sales_month": "2026-02", "total_sales": 792400}],
                "chart_config": {"chart_type": "bar", "x_column": "sales_month", "y_column": "total_sales"},
            },
        },
        {"role": "user", "content": "explain the bar chart above", "payload": None},
    ]
    ctx = build_context_from_messages(messages, exclude_trailing_user=True)
    assert "explain the bar chart above" not in ctx
    assert "Feb vs Mar sales" in ctx
    assert "792400" in ctx


def test_build_context_empty_when_only_current_user():
    messages = [{"role": "user", "content": "hello", "payload": None}]
    assert build_context_from_messages(messages, exclude_trailing_user=True) == ""
