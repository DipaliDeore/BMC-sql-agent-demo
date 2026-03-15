"""
error_handlers.py - Global Error Handlers (Module 5)
-----------------------------------------------------
This file is responsible for:
    - Defining custom error handlers for the FastAPI app
    - Returning clean JSON responses instead of ugly stack traces

Handlers:
    1. Generic Exception → 500 Internal Server Error
    2. RequestValidationError → 422 Invalid Request
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError


def register_error_handlers(app: FastAPI):
    """
    Register all global error handlers on the FastAPI app.

    This function is called from main.py during app startup.
    It adds two exception handlers to the app:
        1. A generic handler for all unhandled exceptions (500)
        2. A handler for request validation errors (422)

    Args:
        app (FastAPI): The FastAPI application instance.
    """

    # ── Handler 1: Generic 500 Error ─────────────────────────────────────
    # This catches ANY unhandled exception that occurs in the app.
    # Instead of showing a raw error, it returns a clean JSON response.
    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        """Handle any unhandled exception with a 500 JSON response."""
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "detail": str(exc)
            }
        )

    # ── Handler 2: Request Validation Error ──────────────────────────────
    # This catches errors when the request body doesn't match the
    # expected format (e.g., missing the "question" field in /api/query).
    # Returns a 422 response with details about what went wrong.
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handle request validation errors with a 422 JSON response."""
        return JSONResponse(
            status_code=422,
            content={
                "error": "Invalid request",
                "detail": str(exc)
            }
        )
