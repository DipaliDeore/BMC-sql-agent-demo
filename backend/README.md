# SQL Agent Demo — Backend

FastAPI backend that converts natural language questions into SQL queries using **LangChain** and **Google Gemini**, then executes them against a **TiDB Cloud / MySQL** database.

## Quick Start

```bash
# 1. Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables
# Edit .env and fill in your credentials (see .env file)

# 4. Start the server
uvicorn app.main:app --reload
```

The server will start at **http://localhost:8000**.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/health` | Health check – returns `{"status":"running"}` |
| `POST` | `/api/query` | Submit a natural language question |
| `GET`  | `/api/schema` | Returns the current DB schema |
| `GET`  | `/docs` | Interactive Swagger UI |

### POST /api/query

**Request body:**
```json
{ "question": "Show me the top 5 customers by revenue" }
```

**Response:**
```json
{
  "question": "Show me the top 5 customers by revenue",
  "sql": "SELECT `customer_name`, SUM(`revenue`) AS `total` FROM `orders` GROUP BY `customer_name` ORDER BY `total` DESC LIMIT 5;",
  "results": [...]
}
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google Gemini API key |
| `DB_HOST` | TiDB Cloud / MySQL host |
| `DB_PORT` | Database port (default: 4000 for TiDB) |
| `DB_USER` | Database username |
| `DB_PASSWORD` | Database password |
| `DB_NAME` | Database name |

## File Structure

```
backend/
├── app/
│   ├── __init__.py       # Package marker
│   ├── main.py           # FastAPI app, CORS, entry point
│   ├── config.py         # Loads .env variables
│   ├── database.py       # DB connection, query execution, schema retrieval
│   ├── sql_generator.py  # LangChain + Gemini → SQL
│   ├── query_validator.py# Safety checks (SELECT-only, no injection)
│   └── routes.py         # API route definitions
├── .env                  # Secret credentials (do NOT commit)
├── requirements.txt      # Python dependencies
└── README.md             # This file
```
