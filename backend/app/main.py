"""
main.py - FastAPI Application Entry Point (Module 5)
-----------------------------------------------------
This file is responsible for:
    - Creating the FastAPI app instance
    - Adding CORS middleware
    - Registering global error handlers
    - Including the API router from routes.py
    - Defining the health check endpoint

Run with:
    cd backend
    uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import router
from app.services.feedback_service import feedback_router
from app.error_handlers import register_error_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.checkpointer import init_checkpointer, shutdown_checkpointer
    from app.chat_store import init_chat_schema

    init_checkpointer()
    init_chat_schema()
    yield
    shutdown_checkpointer()


# ── Step 1: Create the FastAPI Application ────────────────────────────────────
app = FastAPI(
    title="AI SQL Agent",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Step 2: Add CORS Middleware ───────────────────────────────────────────────
# This allows the frontend (running on port 5173) to make API requests
# to this backend server without being blocked by the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Step 3: Register Global Error Handlers ───────────────────────────────────
# This sets up custom handlers for unhandled exceptions and validation errors.
# The handlers are defined in error_handlers.py to keep main.py clean.
register_error_handlers(app)


# ── Step 4: Include API Routes ───────────────────────────────────────────────
# All API endpoints (test-db, schema, query) are defined in routes.py.
# The router adds a /api prefix to all routes automatically.
app.include_router(router)
# POST /feedback (spec path at app root, not under /api)
app.include_router(feedback_router)


# ── Step 5: Health Check Endpoint ────────────────────────────────────────────

@app.get("/")
async def health_check():
    """
    Health check endpoint to verify the server is running.

    URL: GET /
    Returns a JSON response with the server status and version.
    """
    return {
        "status": "AI SQL Agent is running",
        "version": "1.0.0"
    }
