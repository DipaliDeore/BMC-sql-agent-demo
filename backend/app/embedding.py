"""
embedding.py - OpenAI embeddings for semantic cache
---------------------------------------------------
Generates embeddings using OpenAI text-embedding-3-small. Store and search
both use ``get_embedding()`` so vectors are comparable (same model + same
normalization).

Optional normalization collapses month names and common date shapes so queries
like "data for January" and "data for February" embed closer for retrieval.
"""

import re
from typing import List, Optional

from app import config

EMBEDDING_MODEL = "text-embedding-3-small"
_openai_client = None


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        if not (config.OPENAI_API_KEY or "").strip():
            return None
        from openai import OpenAI

        _openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _openai_client

_MONTH_PATTERN = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b",
    re.IGNORECASE,
)
_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")
_DATE_SLASH_PATTERN = re.compile(
    r"\b\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?\b",
)


def normalize_text(text: str) -> str:
    """Lowercase, trim, collapse whitespace."""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_query_for_embedding(text: str) -> str:
    """
    Normalize text before embedding: basic cleanup + replace month/date tokens
    so semantically similar time-range questions cluster in vector space.
    """
    t = normalize_text(text)
    t = _MONTH_PATTERN.sub("<month>", t)
    t = _YEAR_PATTERN.sub("<year>", t)
    t = _DATE_SLASH_PATTERN.sub("<date>", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def get_embedding(text: str) -> Optional[List[float]]:
    """
    Embedding for ``text`` using EMBEDDING_MODEL. Returns None if unavailable.

    Uses ``normalize_query_for_embedding`` so Pinecone upserts and queries
    stay aligned.
    """
    if not text:
        return None

    try:
        client = _get_openai_client()
        if client is None:
            return None

        normalized = normalize_query_for_embedding(text)
        response = client.embeddings.create(
            input=[normalized],
            model=EMBEDDING_MODEL,
        )
        if response.data and len(response.data) > 0:
            return response.data[0].embedding
        return None
    except Exception:
        return None
