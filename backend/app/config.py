"""
config.py
---------
Loads all environment variables from the .env file and exports them
as module-level constants for use across the application.

Do NOT hardcode any credentials here — always use the .env file.
"""

import os
from dotenv import load_dotenv

# Load variables from backend/.env into the environment
load_dotenv()

# ── Google Gemini ──────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

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

# ── OpenAI (embeddings for OpenSearch k-NN cache; text-embedding-3-small) ───────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

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


