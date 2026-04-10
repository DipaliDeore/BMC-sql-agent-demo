"""JSON-safe conversion for DB values and nested structures."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal


def make_json_serializable(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()

    if isinstance(obj, Decimal):
        return float(obj)

    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8")
        except Exception:
            return str(obj)

    if isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [make_json_serializable(i) for i in obj]

    return obj
