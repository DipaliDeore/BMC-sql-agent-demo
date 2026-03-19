"""
pinecone_client.py - Pinecone client for semantic cache
--------------------------------------------------------
Initializes the Pinecone client and provides access to the vector index
used for caching question → SQL pairs. Uses API key from .env (PINECONE_API_KEY).

The index is created automatically if it does not exist, with dimension 1536
to match OpenAI text-embedding-3-small. If Pinecone is not configured,
get_index() returns None and the rest of the app skips caching (no failure).
"""

from typing import Optional

from app import config

# Lazy-initialized Pinecone client and index (avoid touching Pinecone at import time)
_pinecone_client = None
_index = None

# Embedding dimension for OpenAI text-embedding-3-small (required for index creation)
EMBEDDING_DIMENSION = 1536


def get_pinecone_index():
    """
    Return the Pinecone index for the SQL cache, or None if Pinecone is not configured.

    Creates the index if it does not exist (serverless, cosine metric).
    On any failure (missing key, network, etc.), returns None so the app
    can continue without semantic cache.

    Returns:
        Optional[pinecone.Index]: The index instance, or None if disabled/failed.
    """
    global _pinecone_client, _index

    if not config.PINECONE_API_KEY or not config.PINECONE_API_KEY.strip():
        return None

    if _index is not None:
        return _index

    try:
        from pinecone import Pinecone, ServerlessSpec

        _pinecone_client = Pinecone(api_key=config.PINECONE_API_KEY)
        index_name = config.PINECONE_INDEX_NAME or "sql-agent-cache"

        # Ensure index exists (create if not) so we can upsert/query
        if not _pinecone_client.has_index(name=index_name):
            _pinecone_client.create_index(
                name=index_name,
                dimension=EMBEDDING_DIMENSION,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )

        _index = _pinecone_client.Index(index_name)
        return _index

    except Exception:
        # Do not leak exception details; cache is optional
        return None
