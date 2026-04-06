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

# ── OpenAI (embeddings for Pinecone; text-embedding-3-small) ───────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

# ── SQL retry configuration ──────────────────────────────────────────────────────
MAX_SQL_RETRIES = int(os.getenv("MAX_SQL_RETRIES", "3"))

# ── Multi-query analysis (LLM splitter + cache) ────────────────────────────────────
MAX_MULTI_RETRIES = int(os.getenv("MAX_MULTI_RETRIES", "2"))
MAX_SUB_QUERIES = int(os.getenv("MAX_SUB_QUERIES", "4"))
MAX_QUERY_LENGTH = int(os.getenv("MAX_QUERY_LENGTH", "400"))
MAX_ANALYSIS_CACHE_SIZE = int(os.getenv("MAX_ANALYSIS_CACHE_SIZE", "100"))
