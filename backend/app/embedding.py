"""
embedding.py - OpenAI embeddings for semantic cache
---------------------------------------------------
Generates embeddings using OpenAI text-embedding-3-small. Used by the
Pinecone store and search modules to vectorize questions for similarity search.

Requires OPENAI_API_KEY in .env. On failure (missing key, API error), returns None
so callers can skip cache operations without breaking the main flow.
"""

from typing import List, Optional

from app import config

# Model used for embeddings (dimension 1536)
EMBEDDING_MODEL = "text-embedding-3-small"


def get_embedding(text: str) -> Optional[List[float]]:
    """
    Generate a single embedding vector for the given text.

    Uses OpenAI text-embedding-3-small. If OpenAI is not configured or
    the API call fails, returns None so callers can fall back to non-cached behavior.

    Args:
        text: Input string to embed (e.g. user question).

    Returns:
        List of 1536 floats, or None if embedding could not be generated.
    """
    if not text or not (config.OPENAI_API_KEY or "").strip():
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=config.OPENAI_API_KEY)
        response = client.embeddings.create(
            input=[text],
            model=EMBEDDING_MODEL,
        )
        if response.data and len(response.data) > 0:
            return response.data[0].embedding
        return None
    except Exception:
        return None
