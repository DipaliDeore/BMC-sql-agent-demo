# SQL Agent Demo

An **AI-powered SQL agent** that answers questions in plain English: it plans SQL with tools, validates and runs **safe `SELECT`** statements against your database, and returns results in a chat UI—with optional streaming, charts, semantic cache, and conversation memory.

**Backend:** FastAPI, LangChain, **LangGraph**, **Google Gemini** (primary LLM), optional **OpenAI** (embeddings + vision). **Frontend:** React 18, Vite, Tailwind CSS, Recharts. **Data:** **TiDB Cloud** or any MySQL-compatible server (8.0+).

---

## Features

- Chat UI with **conversation threads** (list, create, rename, delete) when Postgres-backed chat storage is configured; in-memory fallback otherwise
- **LangGraph agent** with SQL tools (`agent_executor`, `tools/sql_tools`) instead of a single-shot SQL string
- **Streaming** endpoint (`POST /api/query/stream`) with SSE for tokens, status, rows, and final payload
- **SQL safety** via `query_validator` (dangerous input + non-SELECT blocking)
- **Results** as tables; **charts** (line, bar, pie) via Recharts; **SQL viewer** with syntax highlighting
- **Excel export** for larger result sets (download via `/api/export/{filename}.xlsx`)
- **Thumbs feedback** (`POST /feedback`)—positive feedback can feed **semantic cache** when OpenSearch + OpenAI embeddings are configured; thumbs-down can alert a **Slack channel** via `SLACK_FEEDBACK_WEBHOOK_URL`
- **Similar past queries** (OpenSearch k-NN) when cache stack is enabled
- **Image attachments** in chat: vision pipeline (OpenAI) with configurable limits (`CHAT_IMAGE_*`)
- **Hybrid conversation memory** (optional): rolling summary + structured memory in Postgres—see [docs/MEMORY.md](docs/MEMORY.md)
- **Follow-up context**: prior turns (including vision/chart replies from `chat_store`) are injected into the agent so questions like “explain the chart above” use saved SQL, results, and `chart_config`
- **Schema sync**: background job captures MySQL schema into a **TTL cache**, indexes table/FK chunks in **OpenSearch** (`OPENSEARCH_SCHEMA_INDEX_NAME`), and **clears the semantic query cache** when the schema hash changes
- **Cross-chat global memory**: one evolving summary in Postgres `global_memory` (single user); merged when you **New chat**, **switch chats**, **delete a chat**, on **app load**, on **first query** (pending catch-up), or on **tab close** (best-effort)
- **What-if analysis**: hypothetical questions (e.g. “What if sales increased by 10%?”) run **simulated SELECT** queries (baseline vs scenario), bar chart + comparison table — no database writes
- **Statistical forecasting**: predict/forecast questions (e.g. “Predict next 3 months sales”) fetch historical time-series via SQL, run **ARIMA** (or linear fallback) in Python, and show actual + projected values on a line chart with caveats
- **Query freshness**: open-ended metric questions (e.g. total revenue) bypass stale semantic-cache SQL and chat memory so answers always hit the live database
- **LangGraph checkpoints** + chat schema on **PostgreSQL** when `POSTGRES_URI` is set; otherwise in-memory

---

## Tech stack

| Layer        | Technology |
| ------------ | ---------- |
| Backend      | Python 3.10+, FastAPI, Uvicorn |
| Orchestration | LangGraph, LangChain, LangSmith (tracing) |
| Primary LLM  | Google Gemini (`gemini-2.5-flash` in agent; `gemini-2.5-flash-lite` for memory summaries) |
| Database     | MySQL-compatible (TiDB Cloud default in docs); `mysql-connector-python` |
| Forecasting  | `pandas` + `statsmodels` (ARIMA with linear fallback) |
| Optional cache | OpenSearch + OpenAI `text-embedding-3-small` |
| Optional vision | OpenAI Chat Completions (`OPENAI_VISION_MODEL`, default `gpt-4o-mini`) |
| Persistence  | PostgreSQL (`POSTGRES_URI`) for checkpoints + `chat_store` + optional `bmcs_thread_memory` |
| Frontend     | React 18, Vite 5, Tailwind CSS 3, Axios, react-markdown, react-syntax-highlighter, Recharts |

---

## Getting started

### Prerequisites

- Python 3.10+
- Node.js 18+
- [Google Gemini API key](https://aistudio.google.com/) (required for the agent)
- TiDB Cloud or **MySQL 8.0+** reachable from the backend
- **Optional:** [OpenAI API key](https://platform.openai.com/) (embeddings + vision), OpenSearch 2.x, PostgreSQL 15+, Slack Incoming Webhook (thumbs-down alerts)

### 1. Repository layout

```
BMC-sql-agent-demo/          # or your clone folder name
├── backend/
├── frontend/
└── docs/
    └── MEMORY.md          # hybrid memory env vars and behavior
```

### 2. Backend

```bash
cd backend

python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
```

Copy **`backend/.env.example`** to **`backend/.env`** and fill in your keys (see [Environment variables](#environment-variables)). Then:

```bash
uvicorn app.main:app --reload
```

- API base: `http://localhost:8000`
- Root status JSON: `GET http://localhost:8000/`
- Swagger: `http://localhost:8000/docs`

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

- Dev server (Vite default): `http://localhost:5173`  
  CORS in `main.py` also allows `http://localhost:5174`.

---

## Project structure

```
backend/
├── app/
│   ├── main.py                 # FastAPI app, CORS, lifespan, routers
│   ├── config.py               # Environment variables
│   ├── routes.py               # /api/* HTTP + streaming query + chats + export
│   ├── database.py             # MySQL connection, schema, query execution
│   ├── query_validator.py      # SQL / input safety
│   ├── agent_executor.py       # LangGraph + Gemini tool agent
│   ├── tools/sql_tools.py      # Agent SQL tools
│   ├── query_stream.py         # SSE streaming for /api/query/stream
│   ├── question_planner.py     # Intent routing (forecast, what-if, trend, etc.)
│   ├── forecast_pipeline.py    # ARIMA / linear statistical forecasting
│   ├── trend_pipeline.py       # Time-series trend SQL + charts
│   ├── what_if_pipeline.py     # Hypothetical scenario comparison (read-only)
│   ├── query_freshness.py      # Live DB re-query for open metric questions
│   ├── pipeline_sql_utils.py   # Shared SQL helpers for pipelines
│   ├── chat_store.py           # Chat threads + messages (Postgres or memory)
│   ├── checkpointer.py         # LangGraph Postgres (or memory) checkpoints
│   ├── thread_memory.py        # Hybrid memory persistence
│   ├── memory/                 # Trim, digest, summary, structured memory pipeline
│   ├── search.py / store.py    # Semantic cache search + store
│   ├── embedding.py            # OpenAI embeddings for cache
│   ├── opensearch_client.py
│   ├── vision_gate.py          # OpenAI vision for images + charts
│   ├── excel_export.py         # XLSX generation
│   ├── response_formatting.py  # Narratives merged with model explanations
│   ├── services/feedback_service.py   # POST /feedback
│   ├── services/slack_notify.py         # Thumbs-down Slack webhook alerts
│   └── ...
├── exports/                    # Generated Excel files (served via /api/export)
├── scripts/postgres_app_grants.sql    # DB grants hint for non-superuser Postgres
├── requirements.txt
└── README.md

frontend/
├── src/
│   ├── api/agent.js            # Axios + SSE client
│   ├── pages/ChatPage.jsx
│   ├── components/
│   │   ├── ChatWindow.jsx
│   │   ├── MessageBubble.jsx
│   │   ├── Sidebar.jsx
│   │   ├── ResultTable.jsx
│   │   ├── SqlViewer.jsx
│   │   ├── ChartPanel.jsx + *ChartViewer.jsx
│   │   ├── MessageFeedback.jsx
│   │   └── ...
│   ├── App.jsx
│   ├── main.jsx
│   └── index.css
├── package.json
├── vite.config.js
├── tailwind.config.js
└── postcss.config.js
```

---

## Environment variables

Minimum for a local demo (Gemini + MySQL):

```env
GEMINI_API_KEY=your_gemini_api_key_here

DB_HOST=your-host
DB_PORT=4000
DB_USER=your_username
DB_PASSWORD=your_password
DB_NAME=sql_agent_demo
# Optional TiDB TLS:
# DB_CA_CERT=path/to/ca.pem
```

**Never commit `.env`.** It should stay listed in `.gitignore`.

### Common optional variables

| Variable | Purpose |
| -------- | ------- |
| `POSTGRES_URI` | `postgresql://...` — LangGraph checkpoints + chat UI persistence (see `checkpointer.py`, `chat_store.py`) |
| `SUMMARY_GEMINI_API_KEY` | Override Gemini key used only for summarization (defaults to `GEMINI_API_KEY`) |
| `OPENSEARCH_URL` / `OPENSEARCH_INDEX_NAME` | Semantic question→SQL cache index |
| `OPENAI_API_KEY` | Embeddings (`text-embedding-3-small`) for cache; also vision if used |
| `OPENAI_VISION_MODEL` | Vision model (default `gpt-4o-mini`) |
| `HYBRID_MEMORY_ENABLED` | `true` to enable hybrid memory (full list in [docs/MEMORY.md](docs/MEMORY.md)) |
| `MAX_SQL_RETRIES`, `MAX_RESULT_ROWS`, `EXCEL_INLINE_LIMIT` | Agent retries, row cap, Excel threshold |
| `FORECAST_MIN_HISTORY_POINTS`, `FORECAST_DEFAULT_HORIZON` | Minimum history rows and default forecast horizon (see `forecast_pipeline.py`) |
| `SLACK_FEEDBACK_WEBHOOK_URL` | Slack Incoming Webhook URL for thumbs-down alerts |
| `SLACK_FEEDBACK_ENABLED`, `SLACK_FEEDBACK_TIMEOUT_SECONDS` | Toggle Slack alerts (default on) and HTTP timeout |

Full hybrid-memory knobs (`RECENT_MESSAGE_CAP`, `SUMMARY_TRIGGER_MESSAGES`, etc.) are documented in **[docs/MEMORY.md](docs/MEMORY.md)**. See **`backend/.env.example`** for the complete list of tunables.

---

## API reference

| Method | URL | Description |
| ------ | --- | ----------- |
| `GET` | `/` | Server status JSON |
| `GET` | `/api/test-db` | Test MySQL connectivity |
| `GET` | `/api/schema` | Database schema for the agent (TTL-cached; `?force_refresh=true` for live read) |
| `GET` | `/api/schema/status` | Schema cache + sync status (hash, graph counts, last sync) |
| `POST` | `/api/schema/sync` | Run schema sync now (re-index vectors / invalidate query cache if changed) |
| `GET` | `/api/memory/global` | Current cross-chat memory summary |
| `POST` | `/api/memory/merge-chat` | Merge a closing chat into global memory (body: `chat_id`) |
| `POST` | `/api/memory/merge-pending` | Merge all unmerged chats (optional body: `exclude_chat_id`) |
| `POST` | `/api/query` | Natural language question → SQL + results + narrative (JSON) |
| `POST` | `/api/query/stream` | Same pipeline over **SSE** |
| `GET` | `/api/chats` | List chat threads |
| `POST` | `/api/chats` | Create chat (optional body with `title`) |
| `GET` | `/api/chats/{chat_id}/messages` | Messages for a thread |
| `PATCH` | `/api/chats/{chat_id}` | Rename chat |
| `DELETE` | `/api/chats/{chat_id}` | Delete chat |
| `GET` | `/api/export/{filename}` | Download generated `.xlsx` (no path traversal) |
| `POST` | `/feedback` | User feedback (thumbs); see `feedback_service.py` |

OpenAPI details: `/docs`.

---

## Example questions

Once your database has tables, try prompts like:

**Standard SQL**

- *"Show me the top 10 customers by total orders"*
- *"How many orders were placed this month?"*
- *"List products with price greater than 50"*
- *"What is the average order value per region?"*

**Trends & comparisons**

- *"Show monthly revenue trend for the last 12 months"*
- *"Compare sales by region this year vs last year"*

**What-if scenarios** (simulated `SELECT`; no writes)

- *"What if sales increased by 10%?"*
- *"What would revenue look like if we raised prices by 5%?"*

**Forecasting** (requires enough historical time-series data)

- *"Predict next 3 months sales"*
- *"Forecast revenue for the next quarter"*

---

## Tests (backend)

From `backend/` with the venv active:

```bash
pytest
```
