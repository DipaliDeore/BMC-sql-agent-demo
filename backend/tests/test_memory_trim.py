# pyrefly: ignore [missing-import]
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.memory.trim import last_human_message_index, trim_recent_messages


def test_trim_recent_messages_keeps_suffix_order():
    msgs = [
        HumanMessage(content="a"),
        AIMessage(content="b"),
        HumanMessage(content="c"),
    ]
    out = trim_recent_messages(msgs, cap=2)
    assert len(out) == 2
    assert out[0].content == "b"
    assert out[1].content == "c"


def test_last_human_message_index():
    msgs = [
        HumanMessage(content="old"),
        AIMessage(content="x"),
        ToolMessage(content="{}", tool_call_id="1"),
        HumanMessage(content="new"),
    ]
    assert last_human_message_index(msgs) == 3


def test_trim_noop_when_under_cap():
    msgs = [HumanMessage(content="only")]
    assert trim_recent_messages(msgs, cap=30) == msgs
