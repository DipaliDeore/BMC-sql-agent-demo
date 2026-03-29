"""
search.py - Pinecone semantic retrieval for the SQL assistant
-------------------------------------------------------------
Embedding-based similarity (cosine via Pinecone index). Retrieves top-k past
(question, SQL) pairs above a similarity threshold and returns them for prompt
injection — not for exact string matching.
"""

from __future__ import annotations

import math
from typing import Any

from app.embedding import get_embedding
from app.pinecone_client import get_pinecone_index

# Minimum similarity in [0, 1] after ``_similarity_score_to_unit_interval`` (see above).
SIMILARITY_THRESHOLD = 0.78

# Number of references passed to the LLM after filtering
REFERENCE_TOP_K = 5

# Fetch more neighbors from Pinecone, then filter by threshold (improves recall)
_OVERFETCH_FACTOR = 4
_OVERFETCH_MIN = 16
_OVERFETCH_CAP = 100


def _similarity_score_to_unit_interval(raw: float) -> float:
    """
    Map a Pinecone match score to a value in [0, 1] for APIs and the UI.

    Indexes use ``metric=\"cosine\"``; Pinecone documents cosine similarity in [-1, 1]
    for unit vectors. In practice, floating-point noise or server behavior can yield
    values slightly outside that range (e.g. just above 1.0). We clamp to [0, 1] so
    consumers always see a proper similarity in the expected range.
    """
    try:
        x = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(x):
        return 0.0
    return max(0.0, min(1.0, x))


def _matches_from_results(results: Any) -> list[dict[str, Any]]:
    """Convert Pinecone query results to normalized match dicts."""
    matches: list[dict[str, Any]] = []
    if not results or not getattr(results, "matches", None):
        return matches

    for match in results.matches:
        score = getattr(match, "score", None)
        if score is None:
            continue
        metadata = getattr(match, "metadata", None) or {}
        matches.append(
            {
                "score": _similarity_score_to_unit_interval(score),
                "question": metadata.get("question") or "",
                "sql": metadata.get("sql") or "",
            }
        )
    return matches


def find_similar_queries(question: str, top_k: int | None = None) -> list[dict[str, Any]]:
    """
    Semantic similarity search: embed ``question``, query Pinecone, keep matches
    with cosine similarity >= SIMILARITY_THRESHOLD, return up to ``top_k``.

    If nothing clears the threshold, returns [] (caller proceeds without cache).

    Args:
        question: Current user question (any natural phrasing).
        top_k: Max references (default REFERENCE_TOP_K).

    Returns:
        List of ``{"score", "question", "sql"}`` with ``score`` in ``[0, 1]``, sorted
        by descending score.
    """
    if not question or not question.strip():
        return []

    k = REFERENCE_TOP_K if top_k is None else max(1, top_k)
    fetch_n = min(_OVERFETCH_CAP, max(_OVERFETCH_MIN, k * _OVERFETCH_FACTOR))

    try:
        embedding = get_embedding(question)
        if not embedding:
            return []

        index = get_pinecone_index()
        if index is None:
            return []

        results = index.query(
            vector=embedding,
            top_k=fetch_n,
            include_metadata=True,
        )

        matches = _matches_from_results(results)
        filtered = [
            m
            for m in matches
            if (m.get("sql") or "").strip() and m["score"] >= SIMILARITY_THRESHOLD
        ]
        filtered.sort(key=lambda x: x["score"], reverse=True)
        return filtered[:k]
    except Exception:
        return []
