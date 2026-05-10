import json

# pyrefly: ignore [missing-import]
from langchain_core.messages import ToolMessage

from app.memory.tool_digest import compress_tool_message_content


def test_compress_tool_message_large_results():
    payload = {
        "success": True,
        "sql": "SELECT 1",
        "row_count": 500,
        "results": [{"id": i, "v": "x" * 20} for i in range(500)],
    }
    msg = ToolMessage(content=payload, tool_call_id="call-1")
    out = compress_tool_message_content(msg)
    assert isinstance(out.content, str)
    assert "500" in out.content or "500 row" in out.content
    assert len(out.content) < len(json.dumps(payload))


def test_compress_tool_message_small_unchanged_structure():
    msg = ToolMessage(content={"success": True, "results": [{"a": 1}]}, tool_call_id="x")
    out = compress_tool_message_content(msg)
    assert out.tool_call_id == "x"
