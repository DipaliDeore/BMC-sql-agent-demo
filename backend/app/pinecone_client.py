"""
pinecone_client.py - Pinecone client for semantic cache
--------------------------------------------------------
Initializes the Pinecone client and provides access to the vector index
used for caching question → SQL pairs. Uses API key from .env (PINECONE_API_KEY).

The index must already exist in Pinecone (create it in the console; dimension 1536,
cosine). If Pinecone is not configured or the index is missing, returns None and
the app skips semantic cache (no failure).
"""

from typing import Optional

from app import config

# Lazy-initialized Pinecone client and index (avoid touching Pinecone at import time)
_pinecone_client = None
_index = None
_pinecone_unavailable = False

# Embedding dimension for OpenAI text-embedding-3-small (required for index creation)
EMBEDDING_DIMENSION = 1536


def get_pinecone_index():
    """
    Return the Pinecone index for the SQL cache, or None if Pinecone is not configured.

    On any failure (missing key, missing index, network, etc.), returns None so the
    app can continue without semantic cache.

    Returns:
        Optional[pinecone.Index]: The index instance, or None if disabled/failed.
    """
    global _pinecone_client, _index, _pinecone_unavailable

    if not config.PINECONE_API_KEY or not config.PINECONE_API_KEY.strip():
        return None

    if _index is not None:
        return _index
    if _pinecone_unavailable:
        return None

    try:
        from pinecone import Pinecone

        _pinecone_client = Pinecone(api_key=config.PINECONE_API_KEY)
        index_name = config.PINECONE_INDEX_NAME or "sql-agent-cache"

        # Do not create indexes on the request path — provisioning can take minutes and
        # blocks every first request. Create the index in the Pinecone console (or a
        # one-off script) if you want semantic cache.
        if not _pinecone_client.has_index(name=index_name):
            _pinecone_unavailable = True
            return None

        _index = _pinecone_client.Index(index_name)
        return _index

    except Exception:
        _pinecone_unavailable = True
        return None
