from __future__ import annotations

from collections.abc import Sequence

# pyrefly: ignore [missing-import]
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
    Ensures the trimmed sequence starts with a HumanMessage to avoid breaking 
    AI <-> Tool call sequences which causes Gemini ClientError 400.
    """
    seq = list(messages)
    if cap <= 0 or len(seq) <= cap:
        return seq
    
    start_idx = len(seq) - cap
    for i in range(start_idx, len(seq)):
        if isinstance(seq[i], HumanMessage):
            return seq[i:]
            
    # Fallback if no HumanMessage in the tail
    idx = last_human_message_index(seq)
    if idx >= 0:
        return seq[idx:]
    return seq[-cap:]
