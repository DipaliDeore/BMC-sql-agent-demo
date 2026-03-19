"""
store.py - Store question + SQL in Pinecone (semantic cache)
------------------------------------------------------------
Stores a (question, sql) pair in the vector index by generating an embedding
for the question and upserting it with metadata. Used after a successful
query execution so future similar questions can reuse the SQL.
"""

import uuid
from typing import Optional

from app.embedding import get_embedding
from app.pinecone_client import get_pinecone_index


def store_query(question: str, sql: str) -> bool:
    """
    Store a question and its corresponding SQL in Pinecone for semantic cache.

    Generates an embedding for the question and upserts a vector with metadata
    { "question": question, "sql": sql }. Does nothing if Pinecone or OpenAI
    is unavailable; returns False in that case so the rest of the app is unchanged.

    Args:
        question: The user's natural language question.
        sql: The validated SQL query that was executed successfully.

    Returns:
        True if the pair was stored successfully, False otherwise (no exception).
    """
    if not question or not sql:
        return False

    embedding = get_embedding(question)
    if not embedding:
        return False

    index = get_pinecone_index()
    if index is None:
        return False

    try:
        vector_id = str(uuid.uuid4())
        index.upsert(
            vectors=[
                {
                    "id": vector_id,
                    "values": embedding,
                    "metadata": {"question": question, "sql": sql},
                }
            ],
        )
        return True
    except Exception:
        return False
