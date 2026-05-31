"""
schema_index.py — Index schema tables/FK edges into OpenSearch for vector search + graph metadata.
"""

from __future__ import annotations

from typing import Any

from app import config
from app.embedding import get_embedding
from app.opensearch_client import EMBEDDING_DIMENSION, get_opensearch_client
from app.schema_snapshot import ForeignKeyEdge, SchemaSnapshot, TableInfo

# pyrefly: ignore [missing-import]
from opensearchpy import helpers


def _schema_index_name() -> str:
    return (getattr(config, "OPENSEARCH_SCHEMA_INDEX_NAME", "") or "sql-agent-schema").strip()


def ensure_schema_index(client: Any) -> bool:
    index_name = _schema_index_name()
    if client.indices.exists(index=index_name):
        return True
    index_body = {
        "settings": {"index.knn": True},
        "mappings": {
            "properties": {
                "embedding": {
                    "type": "knn_vector",
                    "dimension": EMBEDDING_DIMENSION,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "nmslib",
                    },
                },
                "doc_type": {"type": "keyword"},
                "table_name": {"type": "keyword"},
                "text": {"type": "text"},
                "schema_hash": {"type": "keyword"},
                "from_table": {"type": "keyword"},
                "to_table": {"type": "keyword"},
            }
        },
    }
    client.indices.create(index=index_name, body=index_body)
    return True


def build_index_documents(snapshot: SchemaSnapshot) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    schema_hash = snapshot.content_hash

    for table in snapshot.tables:
        text = _table_doc_text(table)
        docs.append(
            {
                "_id": f"table-{schema_hash[:12]}-{table.name}",
                "doc_type": "table",
                "table_name": table.name,
                "text": text,
                "schema_hash": schema_hash,
                "from_table": "",
                "to_table": "",
                "embedding": None,
            }
        )

    for i, edge in enumerate(snapshot.relationships):
        text = (
            f"Foreign key: {edge.table_name}.{edge.column_name} "
            f"references {edge.referenced_table}.{edge.referenced_column}"
        )
        docs.append(
            {
                "_id": f"fk-{schema_hash[:12]}-{i}-{edge.table_name}-{edge.column_name}",
                "doc_type": "fk",
                "table_name": edge.table_name,
                "text": text,
                "schema_hash": schema_hash,
                "from_table": edge.table_name,
                "to_table": edge.referenced_table,
                "embedding": None,
            }
        )

    return docs


def _table_doc_text(table: TableInfo) -> str:
    return f"Table {table.name} with columns: {', '.join(table.columns)}"


def index_schema_snapshot(snapshot: SchemaSnapshot) -> tuple[int, str | None]:
    """
    Replace schema vectors for ``snapshot.content_hash`` in OpenSearch.

    Returns (documents_indexed, error_message).
    """
    client = get_opensearch_client()
    if client is None:
        return 0, "OpenSearch unavailable"

    try:
        ensure_schema_index(client)
        index_name = _schema_index_name()

        # Remove prior schema generation(s)
        try:
            client.delete_by_query(
                index=index_name,
                body={"query": {"match_all": {}}},
                refresh=True,
                conflicts="proceed",
            )
        except Exception:
            pass

        docs = build_index_documents(snapshot)
        actions: list[dict[str, Any]] = []
        for doc in docs:
            emb = get_embedding(doc["text"])
            if not emb:
                continue
            body = {k: v for k, v in doc.items() if k != "_id"}
            body["embedding"] = emb
            actions.append(
                {
                    "_op_type": "index",
                    "_index": index_name,
                    "_id": doc["_id"],
                    "_source": body,
                }
            )

        if not actions:
            return 0, "No schema embeddings produced (check OPENAI_API_KEY)"

        success, errors = helpers.bulk(client, actions, refresh=True, raise_on_error=False)
        if errors:
            return int(success), f"bulk_errors={len(errors)}"
        return int(success), None
    except Exception as exc:
        return 0, str(exc)


def find_relevant_schema_chunks(
    question: str,
    *,
    top_k: int | None = None,
    schema_hash: str | None = None,
) -> list[dict[str, Any]]:
    """k-NN search over schema index (optional RAG for prompts)."""
    if not (question or "").strip():
        return []

    k = top_k or int(getattr(config, "SCHEMA_RAG_TOP_K", 8) or 8)
    embedding = get_embedding(question)
    if not embedding:
        return []

    client = get_opensearch_client()
    if client is None or not client.indices.exists(index=_schema_index_name()):
        return []

    query: dict[str, Any] = {
        "size": k,
        "query": {"knn": {"embedding": {"vector": embedding, "k": k}}},
    }
    if schema_hash:
        query["query"] = {
            "bool": {
                "must": [
                    {"knn": {"embedding": {"vector": embedding, "k": k}}},
                    {"term": {"schema_hash": schema_hash}},
                ]
            }
        }

    try:
        resp = client.search(index=_schema_index_name(), body=query)
        out: list[dict[str, Any]] = []
        for hit in resp.get("hits", {}).get("hits", []):
            src = hit.get("_source") or {}
            out.append(
                {
                    "score": float(hit.get("_score") or 0.0),
                    "doc_type": src.get("doc_type"),
                    "table_name": src.get("table_name"),
                    "text": src.get("text"),
                }
            )
        return out
    except Exception:
        return []


def build_schema_rag_text(question: str, *, schema_hash: str | None = None) -> str:
    """Compact schema excerpt from vector index for a user question."""
    chunks = find_relevant_schema_chunks(question, schema_hash=schema_hash)
    if not chunks:
        return ""
    lines = ["Relevant schema (vector retrieval):"]
    for c in chunks:
        lines.append(f"- [{c.get('doc_type')}] {c.get('text')}")
    return "\n".join(lines)
