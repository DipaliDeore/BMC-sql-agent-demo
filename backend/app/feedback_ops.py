"""
OpenSearch updates for explicit thumbs up / thumbs down on cached (question, SQL) docs.
"""

from __future__ import annotations

from typing import Any

from app import config
from app.opensearch_client import get_opensearch_client


def _clamp_trust(x: float) -> float:
    return max(0.05, min(3.0, x))


def apply_positive_feedback(doc_id: str) -> bool:
    """
    Promote a cached example: increment positive_feedback_count and trust_score.
    """
    client = get_opensearch_client()
    if client is None or not doc_id:
        return False
    try:
        try:
            got = client.get(index=config.OPENSEARCH_INDEX_NAME, id=doc_id)
        except Exception:
            return False
        src: dict[str, Any] = got.get("_source") or {}
        if not src.get("embedding"):
            return False
        pos = int(src.get("positive_feedback_count") or 0) + 1
        neg = int(src.get("negative_feedback_count") or 0)
        trust = _clamp_trust(float(src.get("trust_score") or 1.0) + 0.15)
        src["positive_feedback_count"] = pos
        src["negative_feedback_count"] = neg
        src["trust_score"] = trust
        src.setdefault("suppressed", False)
        client.index(
            index=config.OPENSEARCH_INDEX_NAME,
            id=doc_id,
            body=src,
            refresh=True,
        )
        return True
    except Exception:
        return False


def apply_negative_feedback(doc_id: str) -> bool:
    """
    Demote / suppress: mark document as suppressed so retrieval skips it.
    """
    client = get_opensearch_client()
    if client is None or not doc_id:
        return False
    try:
        try:
            got = client.get(index=config.OPENSEARCH_INDEX_NAME, id=doc_id)
        except Exception:
            return False
        src: dict[str, Any] = got.get("_source") or {}
        if not src.get("embedding"):
            return False
        neg = int(src.get("negative_feedback_count") or 0) + 1
        pos = int(src.get("positive_feedback_count") or 0)
        trust = _clamp_trust(float(src.get("trust_score") or 1.0) - 0.5)
        src["negative_feedback_count"] = neg
        src["positive_feedback_count"] = pos
        src["trust_score"] = trust
        src["suppressed"] = True
        client.index(
            index=config.OPENSEARCH_INDEX_NAME,
            id=doc_id,
            body=src,
            refresh=True,
        )
        return True
    except Exception:
        return False
