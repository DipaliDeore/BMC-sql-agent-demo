"""
opensearch_client.py - OpenSearch client for semantic cache
--------------------------------------------------------
Initializes the OpenSearch client and provides access to the vector index
used for caching question → SQL pairs. Uses OPENSEARCH_URL from .env.

The index is created automatically if it does not exist, with dimension 1536
to match OpenAI text-embedding-3-small and a k-NN mapping for vector search.
"""

from typing import Optional

from opensearchpy import OpenSearch, helpers
import urllib3
from app import config

# Suppress insecure request warnings if using an unverified self-signed cert
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_opensearch_client = None
EMBEDDING_DIMENSION = 1536

def get_opensearch_client() -> Optional[OpenSearch]:
    """
    Return the OpenSearch client for the SQL cache.

    Creates the index if it does not exist.
    On any failure (unreachable, etc.), returns None so the app
    can continue without semantic cache.
    """
    global _opensearch_client

    if not config.OPENSEARCH_URL:
        return None

    if _opensearch_client is not None:
        return _opensearch_client

    try:
        # Create client connection. We'll disable SSL verification since local Docker
        # typically uses self-signed certs or runs plain HTTP.
        client = OpenSearch(
            hosts=[config.OPENSEARCH_URL],
            use_ssl=config.OPENSEARCH_URL.startswith("https"),
            verify_certs=False, 
            ssl_assert_hostname=False,
            ssl_show_warn=False
        )

        # Ping to check if alive
        if not client.ping():
            return None

        index_name = config.OPENSEARCH_INDEX_NAME

        # Ensure index exists (create if not) with KNN settings
        if not client.indices.exists(index=index_name):
            index_body = {
                "settings": {
                    "index.knn": True
                },
                "mappings": {
                    "properties": {
                        "embedding": {
                            "type": "knn_vector",
                            "dimension": EMBEDDING_DIMENSION,
                            "method": {
                                "name": "hnsw",
                                "space_type": "cosinesimil",
                                "engine": "nmslib"
                            }
                        },
                        "question": {"type": "text"},
                        "sql": {"type": "text"},
                        "trust_score": {"type": "float"},
                        "suppressed": {"type": "boolean"},
                    }
                }
            }
            client.indices.create(index=index_name, body=index_body)
        else:
            # Best-effort: ensure ranking fields exist on older indices.
            try:
                client.indices.put_mapping(
                    index=index_name,
                    body={
                        "properties": {
                            "trust_score": {"type": "float"},
                            "suppressed": {"type": "boolean"},
                        }
                    },
                )
            except Exception:
                pass

        _opensearch_client = client
        return _opensearch_client

    except Exception:
        # Do not leak exception details; cache is optional
        return None
