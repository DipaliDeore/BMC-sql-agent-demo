"""
search.py - Retrieve similar queries from Pinecone (semantic cache)
-------------------------------------------------------------------
Finds the most similar cached question to the user's question and returns
the associated SQL if the similarity score is above the configured threshold.
"""

from typing import Optional

from app.embedding import get_embedding
from app.pinecone_client import get_pinecone_index

# Minimum similarity score (cosine) to consider a cache hit; 0.85 = fairly strict match
SIMILARITY_THRESHOLD = 0.85


def find_similar_query(question: str) -> Optional[str]:
    """
    Look up a semantically similar question in the cache and return its SQL if close enough.

    Generates an embedding for the question, queries Pinecone for the nearest
    vector, and returns the cached SQL only if the similarity score is greater
    than SIMILARITY_THRESHOLD (0.85). Otherwise returns None so the app generates
    SQL via the existing AI flow.

    Args:
        question: The user's natural language question.

    Returns:
        The cached SQL string if a similar query was found with score > 0.85,
        otherwise None.
    """
    if not question:
        return None

    embedding = get_embedding(question)
    if not embedding:
        return None

    index = get_pinecone_index()
    if index is None:
        return None

    try:
        results = index.query(
            vector=embedding,
            top_k=1,
            include_metadata=True,
        )

        if not results.matches:
            return None

        match = results.matches[0]
        # Pinecone cosine similarity is in match.score; ensure we have a valid score
        score = getattr(match, "score", None)
        if score is None or score < SIMILARITY_THRESHOLD:
            return None

        metadata = getattr(match, "metadata", None) or {}
        return metadata.get("sql")
    except Exception:
        return None
