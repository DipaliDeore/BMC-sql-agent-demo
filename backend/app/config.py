"""
config.py
---------
Loads all environment variables from the .env file and exports them
as module-level constants for use across the application.

Do NOT hardcode any credentials here — always use the .env file.
"""

import os
from pathlib import Path

# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

# Load backend/.env regardless of process cwd (uvicorn may start from repo root).
_backend_root = Path(__file__).resolve().parent.parent
load_dotenv(_backend_root / ".env")
load_dotenv()  # fallback: cwd-based .env if present

# ── Google Gemini ──────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
SUMMARY_GEMINI_API_KEY: str = os.getenv("SUMMARY_GEMINI_API_KEY", GEMINI_API_KEY)

# ── PostgreSQL (LangGraph checkpoints + chat UI persistence) ───────────────────
# Example: postgresql://user:pass@localhost:5432/mydb
# If unset, the app uses in-memory checkpoints and in-memory chat storage.
#
# PostgreSQL 15+: non-superusers need CREATE on schema public (or use DB owner / postgres).
# Superuser (psql/pgAdmin): GRANT USAGE, CREATE ON SCHEMA public TO your_app_user;
# See backend/scripts/postgres_app_grants.sql
POSTGRES_URI: str = os.getenv("POSTGRES_URI", "").strip()

# ── TiDB Cloud / MySQL Database ────────────────────────────────────────────────
DB_HOST: str     = os.getenv("DB_HOST", "localhost")
DB_PORT: int     = int(os.getenv("DB_PORT", "4000"))
DB_USER: str     = os.getenv("DB_USER", "root")
DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
DB_NAME: str     = os.getenv("DB_NAME", "sql_agent_demo")

# Path to the TiDB Cloud SSL CA certificate file (download from TiDB console)
DB_CA_CERT: str  = os.getenv("DB_CA_CERT", "")

# ── OpenSearch (semantic cache for question → SQL) ─────────────────────────────
OPENSEARCH_URL: str = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
OPENSEARCH_INDEX_NAME: str = os.getenv("OPENSEARCH_INDEX_NAME", "sql-agent-cache")
OPENSEARCH_SCHEMA_INDEX_NAME: str = os.getenv(
    "OPENSEARCH_SCHEMA_INDEX_NAME", "sql-agent-schema"
)

# Schema TTL cache + background sync (OpenSearch schema vectors + cache invalidation)
SCHEMA_CACHE_TTL_SECONDS: int = int(os.getenv("SCHEMA_CACHE_TTL_SECONDS", "300"))
SCHEMA_SYNC_INTERVAL_SECONDS: int = int(os.getenv("SCHEMA_SYNC_INTERVAL_SECONDS", "300"))
SCHEMA_SYNC_ENABLED = os.getenv("SCHEMA_SYNC_ENABLED", "true").strip().lower() in (
    "1",
    "true",
    "yes",
)
SCHEMA_INDEX_ENABLED = os.getenv("SCHEMA_INDEX_ENABLED", "true").strip().lower() in (
    "1",
    "true",
    "yes",
)
SCHEMA_RAG_IN_PROMPT = os.getenv("SCHEMA_RAG_IN_PROMPT", "false").strip().lower() in (
    "1",
    "true",
    "yes",
)
SCHEMA_RAG_TOP_K: int = int(os.getenv("SCHEMA_RAG_TOP_K", "8"))

# ── OpenAI (embeddings for OpenSearch k-NN cache; text-embedding-3-small) ───────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
# Vision gate + chart/image Q&A (Chat Completions image_url)
OPENAI_VISION_MODEL: str = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini").strip()
OPENAI_VISION_TIMEOUT_SECONDS: float = float(os.getenv("OPENAI_VISION_TIMEOUT_SECONDS", "60"))
# Truncated schema appended to OpenAI vision *answer* step only (not the gate).
VISION_SCHEMA_CONTEXT_MAX_CHARS: int = int(os.getenv("VISION_SCHEMA_CONTEXT_MAX_CHARS", "10000"))

# User message image_attachments JSONB — decoded size limits (base64 stored; DB row size bounded)
CHAT_IMAGE_PAYLOAD_MAX_TOTAL_DECODED_BYTES: int = int(
    os.getenv("CHAT_IMAGE_PAYLOAD_MAX_TOTAL_DECODED_BYTES", str(4 * 1024 * 1024))
)
CHAT_IMAGE_PAYLOAD_MAX_PER_IMAGE_DECODED_BYTES: int = int(
    os.getenv("CHAT_IMAGE_PAYLOAD_MAX_PER_IMAGE_DECODED_BYTES", str(2 * 1024 * 1024))
)

# ── SQL retry configuration ──────────────────────────────────────────────────────
MAX_SQL_RETRIES = int(os.getenv("MAX_SQL_RETRIES", "3"))

# ── Multi-query analysis (LLM splitter + cache) ────────────────────────────────────
MAX_MULTI_RETRIES = int(os.getenv("MAX_MULTI_RETRIES", "2"))
MAX_SUB_QUERIES = int(os.getenv("MAX_SUB_QUERIES", "4"))
MAX_QUERY_LENGTH = int(os.getenv("MAX_QUERY_LENGTH", "400"))
MAX_ANALYSIS_CACHE_SIZE = int(os.getenv("MAX_ANALYSIS_CACHE_SIZE", "100"))

# Excel export thresholds
EXCEL_INLINE_LIMIT = int(os.getenv("EXCEL_INLINE_LIMIT", "100"))

# Cap rows returned from any agent SELECT (wrapped as subquery + LIMIT).
MAX_RESULT_ROWS = int(os.getenv("MAX_RESULT_ROWS", "100"))

# Hybrid conversation memory (LangGraph prompt view + bmcs_thread_memory)
HYBRID_MEMORY_ENABLED = os.getenv("HYBRID_MEMORY_ENABLED", "false").strip().lower() in (
    "1",
    "true",
    "yes",
)
RECENT_MESSAGE_CAP = int(os.getenv("RECENT_MESSAGE_CAP", "30"))
SUMMARY_TRIGGER_MESSAGES = int(os.getenv("SUMMARY_TRIGGER_MESSAGES", "60"))
MAX_CONTEXT_TOKENS_SOFT = int(os.getenv("MAX_CONTEXT_TOKENS_SOFT", "120000"))
SUMMARY_MAX_CHARS = int(os.getenv("SUMMARY_MAX_CHARS", "8000"))
STRUCTURED_MEMORY_JSON_MAX_CHARS = int(os.getenv("STRUCTURED_MEMORY_JSON_MAX_CHARS", "4000"))
TOOL_DIGEST_MAX_CHARS = int(os.getenv("TOOL_DIGEST_MAX_CHARS", "6000"))
MEMORY_SUMMARY_DEBOUNCE_MESSAGES = int(os.getenv("MEMORY_SUMMARY_DEBOUNCE_MESSAGES", "8"))

# Cross-chat long-term memory (single user; one row in global_memory)
GLOBAL_MEMORY_ENABLED = os.getenv("GLOBAL_MEMORY_ENABLED", "true").strip().lower() in (
    "1",
    "true",
    "yes",
)
GLOBAL_SUMMARY_MAX_CHARS = int(os.getenv("GLOBAL_SUMMARY_MAX_CHARS", "8000"))


