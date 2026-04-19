"""
Append-only JSONL logs for explicit user feedback and promotion metrics.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOG_DIR = Path(__file__).resolve().parent.parent / "data"
_FEEDBACK_PATH = _LOG_DIR / "feedback.jsonl"
_METRICS_PATH = _LOG_DIR / "metrics.jsonl"


def _append_line(path: Path, record: dict[str, Any]) -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def log_feedback_event(record: dict[str, Any]) -> None:
    """Log thumbs up/down (and metadata) for analysis. Never log secrets."""
    r = {"ts": datetime.now(timezone.utc).isoformat(), **record}
    _append_line(_FEEDBACK_PATH, r)


def log_metric_event(event: str, extra: dict[str, Any] | None = None) -> None:
    """Counters / milestones (e.g. explicit positive promotion)."""
    r = {"ts": datetime.now(timezone.utc).isoformat(), "event": event}
    if extra:
        r.update(extra)
    _append_line(_METRICS_PATH, r)
