"""Classify LLM / provider errors for consistent handling in streams and routes."""


def rate_limited(exc: BaseException) -> bool:
    s = str(exc).lower()
    return "429" in s or "resource_exhausted" in s or "quota" in s
