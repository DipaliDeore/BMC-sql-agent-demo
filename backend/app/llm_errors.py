"""Classify LLM / provider errors and retry rate-limited calls."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def rate_limited(exc: BaseException) -> bool:
    s = str(exc).lower()
    if "429" in s or "resource_exhausted" in s:
        return True
    if "quota" in s and any(
        token in s
        for token in (
            "exceeded",
            "exhausted",
            "limit",
            "rate",
            "429",
            "resource",
        )
    ):
        return True
    return False


def invoke_with_retry(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_delay_seconds: float = 2.0,
) -> T:
    """Run ``fn``; on rate-limit errors, sleep with exponential backoff and retry."""
    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if not rate_limited(exc) or attempt >= max_attempts - 1:
                raise
            delay = base_delay_seconds * (2**attempt)
            print(
                f"[LLM] Rate limited (attempt {attempt + 1}/{max_attempts}), "
                f"retrying in {delay:.1f}s…"
            )
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc
