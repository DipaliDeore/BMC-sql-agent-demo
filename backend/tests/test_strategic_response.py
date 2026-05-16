from app.agent_executor import apply_strategic_response_shape
from app.query_stream import _materialize_http_final
from app.strategic_pipeline import STRATEGIC_RESPONSE_KIND


def test_materialize_http_final_preserves_strategic_explanation():
    tool_result = {
        "status": "success",
        "sql_query": "SELECT 1",
        "explanation": (
            "Returns are highest on Product A. Focus on sizing guides and QA for that SKU."
        ),
        "results": [],
        "row_count": 0,
        "is_multi": False,
        "response_kind": STRATEGIC_RESPONSE_KIND,
    }
    final = _materialize_http_final(
        "How can I reduce product returns?",
        "conv-1",
        tool_result,
        None,
    )
    assert "Product A" in final["explanation"]
    assert "nothing matched" not in final["explanation"].lower()


def test_apply_strategic_response_shape_sets_response_kind():
    summary = {
        "status": "success",
        "explanation": "Actionable advice here.",
        "results": [{"x": 1}],
        "row_count": 1,
        "sql_query": "SELECT 1",
        "is_multi": True,
        "sub_responses": [{"explanation": "ignored"}],
    }
    apply_strategic_response_shape(summary, {"strategy": "strategic_mode"})
    assert summary["response_kind"] == STRATEGIC_RESPONSE_KIND
    assert summary["results"] == []
    assert summary["explanation"] == "Actionable advice here."
