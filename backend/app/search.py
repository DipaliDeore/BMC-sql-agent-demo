"""
search.py - Retrieve similar queries from Pinecone (semantic cache)
-------------------------------------------------------------------
Finds the most similar cached question to the user's question and returns
the associated SQL if the similarity score is above the configured threshold.
"""

from __future__ import annotations

from typing import Any, Optional

from app.embedding import get_embedding
from app.pinecone_client import get_pinecone_index

# Minimum similarity score (cosine) to consider a cache hit; 0.85 = fairly strict match
SIMILARITY_THRESHOLD = 0.85


def _matches_from_results(results: Any) -> list[dict[str, Any]]:
    """Convert Pinecone results to a normalized list of match dicts."""
    matches = []
    if not results or not getattr(results, "matches", None):
        return matches

    for match in results.matches:
        score = getattr(match, "score", None)
        if score is None:
            continue

        metadata = getattr(match, "metadata", None) or {}
        matches.append(
            {
                "score": score,
                "question": metadata.get("question") or "",
                "sql": metadata.get("sql") or "",
            }
        )
    return matches


def find_similar_queries(question: str, top_k: int = 3) -> list[dict[str, Any]]:
    """
    Look up semantically similar cached questions in Pinecone and return up to `top_k` references.

    Generates an embedding for the question, queries Pinecone for the nearest
    vectors, and returns cached references only if similarity scores are greater
    than SIMILARITY_THRESHOLD.

    Args:
        question: The user's natural language question.
        top_k: Number of nearest cached items to consider.

    Returns:
        A list of reference dicts: `{"score", "question", "sql"}` (length <= top_k).
    """
    if not question:
        return []

    try:
        embedding = get_embedding(question)
        if not embedding:
            return []

        index = get_pinecone_index()
        if index is None:
            return []

        results = index.query(
            vector=embedding,
            top_k=top_k,
            include_metadata=True,
        )

        matches = _matches_from_results(results)
        filtered = [
            m
            for m in matches
            if (m.get("sql") or "").strip()
            and m.get("score") is not None
            and float(m["score"]) >= SIMILARITY_THRESHOLD
        ]
        return filtered[:top_k]
    except Exception:
        return []
