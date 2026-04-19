"""
store.py - Store question + SQL in OpenSearch (semantic cache)
---------------------------------------------------------------
Stores a (question, sql) pair in the vector index by generating an embedding
for the question and indexing it. Used after a successful query execution so
future similar questions can retrieve it as a few-shot reference.
"""

import uuid

from app.embedding import get_embedding
from app.opensearch_client import get_opensearch_client
from app import config


def store_query(question: str, sql: str, doc_id: str | None = None) -> bool:
    """
    Store a question and its corresponding SQL in OpenSearch for semantic cache.

    Generates an embedding for the question and indexes a document with
    the vector, question, and sql. Does nothing if
    OpenSearch is unavailable.

    Args:
        question: The user's natural language question.
        sql: The validated SQL query that was executed successfully.
        doc_id: Optional OpenSearch document id (e.g. pre-generated for POST /api/query).

    Returns:
        True if the pair was stored successfully, False otherwise (no exception).
    """
    if not question or not sql:
        return False

    embedding = get_embedding(question)
    if not embedding:
        return False

    client = get_opensearch_client()
    if client is None:
        return False

    try:
        final_id = doc_id if doc_id else str(uuid.uuid4())
        document = {
            "embedding": embedding,
            "question": question,
            "sql": sql,
        }

        client.index(
            index=config.OPENSEARCH_INDEX_NAME,
            id=final_id,
            body=document,
            refresh=True,
        )
        return True
    except Exception:
        return False
