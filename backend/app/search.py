"""
search.py - OpenSearch semantic retrieval for the SQL assistant
-------------------------------------------------------------
Embedding-based similarity (cosine via OpenSearch k-NN index). Retrieves top-k past
(question, SQL) pairs above a similarity threshold and returns them for prompt
injection.
"""

from __future__ import annotations

import math
from typing import Any

from app.embedding import get_embedding
from app.opensearch_client import get_opensearch_client
from app import config

# Minimum similarity (OpenSearch computes cosine based score).
SIMILARITY_THRESHOLD = 0.78

# Number of references passed to the LLM after filtering
REFERENCE_TOP_K = 3

# Fetch more neighbors from Pinecone, then filter by threshold (improves recall)
_OVERFETCH_FACTOR = 3
_OVERFETCH_MIN = 8
_OVERFETCH_CAP = 100

def _similarity_score_to_unit_interval(raw: float) -> float:
    """Clamp score slightly just in case."""
    try:
        x = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(x):
        return 0.0
    return max(0.0, min(1.0, x))


<<<<<<< Updated upstream
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
=======
def _print_rag_terminal(
    question: str,
    *,
    k: int,
    matches: list[dict[str, Any]] | None = None,
    skip_reason: str | None = None,
) -> None:
    """Print user query and top-k OpenSearch neighbors (or skip/error reason) for RAG visibility."""
    print("-----------------------------------")
    print(f'User Query: "{question}"')
    print("\nRetrieved Queries:")
    if skip_reason:
        print(skip_reason)
    else:
        assert matches is not None
        ranked = sorted(matches, key=lambda x: x["score"], reverse=True)[:k]
        if not ranked:
            print("(no hits from OpenSearch)")
        else:
            for i, m in enumerate(ranked, 1):
                q = (m.get("question") or "").strip() or "(empty)"
                print(f'{i}. "{q}" (score: {m["score"]:.2f})')
    print("-----------------------------------")
>>>>>>> Stashed changes


def find_similar_queries(question: str, top_k: int | None = None) -> list[dict[str, Any]]:
    """
    Semantic similarity search: embed `question`, query OpenSearch, keep matches
    with cosine similarity >= SIMILARITY_THRESHOLD, return up to `top_k`.
    """
    if not question or not question.strip():
        return []

    k = REFERENCE_TOP_K if top_k is None else max(1, top_k)
    fetch_n = min(_OVERFETCH_CAP, max(_OVERFETCH_MIN, k * _OVERFETCH_FACTOR))

    try:
        embedding = get_embedding(question)
        if not embedding:
            _print_rag_terminal(
                question,
                k=k,
                skip_reason="(skipped — no embedding; configure OPENAI_API_KEY)",
            )
            return []

<<<<<<< Updated upstream
        index = get_pinecone_index()
        if index is None:
=======
        client = get_opensearch_client()
        if client is None:
            _print_rag_terminal(
                question,
                k=k,
                skip_reason="(skipped — OpenSearch unavailable; check OPENSEARCH_URL and that Docker is running)",
            )
>>>>>>> Stashed changes
            return []

        results = index.query(
            vector=embedding,
            top_k=fetch_n,
            include_metadata=True,
        )

<<<<<<< Updated upstream
        matches = _matches_from_results(results)
=======
        hits = response.get("hits", {}).get("hits", [])
        
        matches = []
        for hit in hits:
            score = hit.get("_score", 0.0)
            source = hit.get("_source", {})
            matches.append({
                "score": _similarity_score_to_unit_interval(score),
                "question": source.get("question", ""),
                "sql": source.get("sql", "")
            })

        _print_rag_terminal(question, k=k, matches=matches)

>>>>>>> Stashed changes
        filtered = [
            m for m in matches
            if (m.get("sql") or "").strip() and m["score"] >= SIMILARITY_THRESHOLD
        ]
        filtered.sort(key=lambda x: x["score"], reverse=True)
        return filtered[:k]

    except Exception:
        _print_rag_terminal(
            question,
            k=k,
            skip_reason="(retrieval failed — see server logs / OpenSearch connectivity)",
        )
        return []
