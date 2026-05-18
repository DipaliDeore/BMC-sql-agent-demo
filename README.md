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
- **Thumbs feedback** (`POST /feedback`)—positive feedback can feed **semantic cache** when OpenSearch + OpenAI embeddings are configured
- **Similar past queries** (OpenSearch k-NN) when cache stack is enabled
- **Image attachments** in chat: vision pipeline (OpenAI) with configurable limits (`CHAT_IMAGE_*`)
- **Hybrid conversation memory** (optional): rolling summary + structured memory in Postgres—see [docs/MEMORY.md](docs/MEMORY.md)
- **LangGraph checkpoints** + chat schema on **PostgreSQL** when `POSTGRES_URI` is set; otherwise in-memory

---

## Tech stack

| Layer        | Technology |
| ------------ | ---------- |
| Backend      | Python 3.10+, FastAPI, Uvicorn |
| Orchestration | LangGraph, LangChain, LangSmith (tracing) |
| Primary LLM  | Google Gemini (`gemini-2.5-flash` in agent; `gemini-2.5-flash-lite` for memory summaries) |
| Database     | MySQL-compatible (TiDB Cloud default in docs); `mysql-connector-python` |
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
- **Optional:** [OpenAI API key](https://platform.openai.com/) (embeddings + vision), OpenSearch 2.x, PostgreSQL 15+

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
│   ├── question_planner.py     # Multi-query / analysis helpers
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

Full hybrid-memory knobs (`RECENT_MESSAGE_CAP`, `SUMMARY_TRIGGER_MESSAGES`, etc.) are documented in **[docs/MEMORY.md](docs/MEMORY.md)**.

---

## API reference

| Method | URL | Description |
| ------ | --- | ----------- |
| `GET` | `/` | Server status JSON |
| `GET` | `/api/test-db` | Test MySQL connectivity |
| `GET` | `/api/schema` | Database schema for the agent |
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

- *"Show me the top 10 customers by total orders"*
- *"How many orders were placed this month?"*
- *"List products with price greater than 50"*
- *"What is the average order value per region?"*

---

## Tests (backend)

From `backend/` with the venv active:

```bash
pytest
```
