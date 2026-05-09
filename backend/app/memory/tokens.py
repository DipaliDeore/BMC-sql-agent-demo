from __future__ import annotations

import json
from collections.abc import Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage


def estimate_messages_tokens(messages: Sequence[BaseMessage]) -> int:
    """
    Rough token estimate without extra deps (chars/4 + JSON penalty for tool payloads).
    """
    total = 0
    for m in messages:
        if isinstance(m, HumanMessage):
            c = m.content if isinstance(m.content, str) else json.dumps(m.content, default=str)
        elif isinstance(m, AIMessage):
            c = m.content if isinstance(m.content, str) else json.dumps(m.content, default=str)
            if getattr(m, "tool_calls", None):
                c += json.dumps(m.tool_calls, default=str)
        elif isinstance(m, ToolMessage):
            c = m.content if isinstance(m.content, str) else json.dumps(m.content, default=str)
            total += len(c) // 3
            continue
        else:
            c = getattr(m, "content", "") or ""
            if not isinstance(c, str):
                c = json.dumps(c, default=str)
        total += max(1, len(c) // 4)
    return int(total)
