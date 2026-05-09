from __future__ import annotations

from collections.abc import Sequence

from langchain_core.messages import BaseMessage, HumanMessage


def last_human_message_index(messages: Sequence[BaseMessage]) -> int:
    """Index of the most recent HumanMessage, or -1 if none."""
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return i
    return -1


def trim_recent_messages(messages: Sequence[BaseMessage], cap: int) -> list[BaseMessage]:
    """
    Keep the last `cap` messages in order. If cap <= 0, return full list as a copy.
    """
    seq = list(messages)
    if cap <= 0 or len(seq) <= cap:
        return seq
    return seq[-cap:]
