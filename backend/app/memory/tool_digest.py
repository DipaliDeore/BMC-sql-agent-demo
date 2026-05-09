from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import ToolMessage

from app import config


def _rows_digest(rows: list[Any]) -> str:
    if not rows:
        return "0 rows"
    n = len(rows)
    first = rows[0] if isinstance(rows[0], dict) else {}
    cols = list(first.keys())[:40] if isinstance(first, dict) else []
    sample = rows[:3] if n <= 3 else rows[:3]
    body = json.dumps(sample, default=str)
    cap = getattr(config, "TOOL_DIGEST_MAX_CHARS", 6000)
    if len(body) > cap:
        body = body[:cap] + "…(truncated)"
    return (
        f"[digest] {n} row(s). Columns: {', '.join(cols) or '?'}. "
        f"Sample (up to 3): {body}"
    )


def compress_tool_message_content(msg: ToolMessage) -> ToolMessage:
    """
    Replace large tabular tool JSON with a compact digest string.
    """
    raw = msg.content
    if isinstance(raw, dict):
        if raw.get("success") and isinstance(raw.get("results"), list):
            digest = _rows_digest(raw["results"])
            extra = {k: raw[k] for k in ("sql", "row_count") if k in raw}
            if extra:
                digest = f"{digest} meta={json.dumps(extra, default=str)}"
            return ToolMessage(
                content=digest,
                tool_call_id=msg.tool_call_id,
                name=getattr(msg, "name", None),
            )
        txt = json.dumps(raw, default=str)
        cap = getattr(config, "TOOL_DIGEST_MAX_CHARS", 6000)
        if len(txt) > cap:
            txt = txt[:cap] + "…(truncated)"
        return ToolMessage(
            content=f"[digest]{txt}",
            tool_call_id=msg.tool_call_id,
            name=getattr(msg, "name", None),
        )
    if isinstance(raw, str) and len(raw) > getattr(config, "TOOL_DIGEST_MAX_CHARS", 6000):
        cap = getattr(config, "TOOL_DIGEST_MAX_CHARS", 6000)
        return ToolMessage(
            content=raw[:cap] + "…(truncated)",
            tool_call_id=msg.tool_call_id,
            name=getattr(msg, "name", None),
        )
    return msg
