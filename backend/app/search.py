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

# Fetch more neighbors from OpenSearch, then filter by threshold (improves recall)
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
                sql_str = (m.get("sql") or "").strip()
                print(f'{i}. "{q}" (sim: {m["score"]:.2f}) -> {sql_str[:50]}...')
    print("-----------------------------------")

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

        client = get_opensearch_client()
        if client is None:
            _print_rag_terminal(
                question,
                k=k,
                skip_reason="(skipped — OpenSearch unavailable; check OPENSEARCH_URL and that Docker is running)",
            )
            return []

        query_body = {
            "size": fetch_n,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": embedding,
                        "k": fetch_n
                    }
                }
            }
        }

        response = client.search(
            index=config.OPENSEARCH_INDEX_NAME,
            body=query_body
        )

        hits = response.get("hits", {}).get("hits", [])

        matches: list[dict[str, Any]] = []
        for hit in hits:
            raw_score = hit.get("_score", 0.0)
            base = _similarity_score_to_unit_interval(raw_score)
            source = hit.get("_source", {}) or {}
            matches.append({
                "score": base,
                "question": source.get("question", ""),
                "sql": source.get("sql", ""),
                "doc_id": (hit.get("_id") or "") or "",
            })

        _print_rag_terminal(question, k=k, matches=matches)

        filtered = [
            m
            for m in matches
            if (m.get("sql") or "").strip()
            and m["score"] >= SIMILARITY_THRESHOLD
        ]
        filtered.sort(key=lambda x: x["score"], reverse=True)
        out = []
        for m in filtered[:k]:
            out.append({
                "score": m["score"],
                "question": m["question"],
                "sql": m["sql"],
                "doc_id": m.get("doc_id") or "",
            })
        return out

    except Exception as e:
        _print_rag_terminal(
            question,
            k=k,
            skip_reason=f"(retrieval failed — error: {e})",
        )
        return []
