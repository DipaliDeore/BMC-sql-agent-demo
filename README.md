# 🤖 SQL Agent Demo

An **AI-powered SQL Agent** that lets you query your database using plain English. Type a question, and the agent generates the SQL, runs it, and returns the results — all in a sleek chat interface.

Built with **FastAPI + LangChain + Google Gemini** on the backend and **React + Tailwind CSS** on the frontend, connected to a **TiDB Cloud (MySQL-compatible)** database.

---

## ✨ Features

- 💬 Chat-style interface for natural language queries
- 🧠 Google Gemini generates accurate SQL from your question
- 🔒 Built-in SQL validator — only safe `SELECT` queries run
- 📋 Query history sidebar for quick re-use
- 📊 Results rendered in a clean data table

---

## 🛠️ Tech Stack

| Layer       | Technology                            |
| ----------- | ------------------------------------- |
| Backend     | Python, FastAPI, LangChain            |
| AI          | Google Gemini (`gemini-flash-latest`) |
| Database    | TiDB Cloud (MySQL-compatible)         |
| Frontend    | React 18, Vite, Tailwind CSS          |
| HTTP Client | Axios                                 |

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- A [Google Gemini API key](https://aistudio.google.com/)
- A [TiDB Cloud](https://tidbcloud.com/) account (or any MySQL 8.0+ server)

### 1. Clone / open the project

```
sql-agent-demo/
├── backend/
└── frontend/
```

### 2. Backend Setup

```bash
cd backend

# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure credentials
# Open .env and fill in your GEMINI_API_KEY, DB_HOST, DB_USER, DB_PASSWORD
```

**Start the backend:**

```bash
uvicorn app.main:app --reload
```

Server runs at → `http://localhost:8000`  
Swagger UI → `http://localhost:8000/docs`

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server
npm run dev
```

Frontend runs at → `http://localhost:5173`

---

## 📁 Project Structure

```
sql-agent-demo/
│
├── backend/
│   ├── app/
│   │   ├── __init__.py           # Package marker
│   │   ├── main.py               # FastAPI app entry point + CORS
│   │   ├── config.py             # Loads environment variables
│   │   ├── database.py           # DB connection, execution, schema
│   │   ├── sql_generator.py      # LangChain + Gemini → SQL
│   │   ├── query_validator.py    # SQL safety validator
│   │   └── routes.py             # API route definitions
│   ├── .env                      # 🔑 Credentials (never commit!)
│   ├── requirements.txt
│   └── README.md
│
└── frontend/
    ├── src/
    │   ├── components/
    │   │   ├── ChatBox.jsx        # Chat feed + input form
    │   │   ├── Message.jsx        # Individual message bubble
    │   │   └── QueryHistory.jsx   # Sidebar query history
    │   ├── pages/
    │   │   └── ChatPage.jsx       # Main page layout
    │   ├── App.jsx
    │   ├── main.jsx
    │   └── index.css
    ├── index.html
    ├── package.json
    ├── tailwind.config.js
    ├── postcss.config.js
    └── vite.config.js
```

---

## 🔐 Environment Variables

Create/edit `backend/.env`:

```env
GEMINI_API_KEY=your_gemini_api_key_here

DB_HOST=your-tidb-host.tidbcloud.com
DB_PORT=4000
DB_USER=your_username
DB_PASSWORD=your_password
DB_NAME=sql_agent_demo
```

> ⚠️ **Never commit `.env` to version control.** Add it to `.gitignore`.

Optional **hybrid conversation memory** (bounded LLM context): set `HYBRID_MEMORY_ENABLED=true` and see **[docs/MEMORY.md](docs/MEMORY.md)** for all related env vars and Postgres table `bmcs_thread_memory`.

---

## 📡 API Reference

| Method | URL           | Description                        |
| ------ | ------------- | ---------------------------------- |
| `GET`  | `/health`     | Server health check                |
| `POST` | `/api/query`  | Submit a natural language question |
| `GET`  | `/api/schema` | View database schema               |

---

## 🧪 Example Queries

Once your database has tables, try questions like:

- _"Show me the top 10 customers by total orders"_
- _"How many orders were placed this month?"_
- _"List all products with a price greater than $50"_
- _"What is the average order value per region?"_
