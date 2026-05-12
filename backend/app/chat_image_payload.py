"""
Pack user image attachments into chat_store user message payload (JSONB).

Decoded byte limits keep rows bounded for Postgres / in-memory store.
"""

from __future__ import annotations

import base64
import re
from typing import Any


def _img_field(im: Any, key: str, default: Any = None) -> Any:
    """Support Pydantic models and plain dicts (FastAPI may hand either to nested lists)."""
    if isinstance(im, dict):
        return im.get(key, default)
    return getattr(im, key, default)


def pack_user_image_attachments_for_storage(
    images: list[Any] | None,
    *,
    max_total_decoded_bytes: int,
    max_per_image_decoded_bytes: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Returns ``(payload_dict, None)`` on success — ``payload_dict`` is
    ``{"image_attachments": [{"media_type", "data_base64"}, ...]}``.

    On failure returns ``(None, user_visible_error_message)`` (caller should map to HTTP 413).
    """
    if not images:
        return None, None

    attachments: list[dict[str, str]] = []
    total = 0

    for im in images:
        mime = _img_field(im, "media_type") or "image/png"
        if isinstance(mime, str):
            mime = mime.strip().lower() or "image/png"
            if mime == "image/jpg":
                mime = "image/jpeg"
            if not mime.startswith("image/"):
                mime = "image/png"
        else:
            mime = "image/png"

        raw = (_img_field(im, "data_base64") or "").strip()
        if "base64," in raw:
            raw = raw.split("base64,", 1)[-1].strip()
        raw = re.sub(r"\s+", "", raw)
        if not raw:
            return None, "Each image must include non-empty base64 data."

        try:
            decoded = base64.b64decode(raw, validate=True)
        except Exception:
            return None, "Invalid base64 in one of the image attachments."

        n = len(decoded)
        if n > max_per_image_decoded_bytes:
            return None, (
                f"Each image must be at most {max_per_image_decoded_bytes // 1024} KB "
                "after decoding for chat storage."
            )
        if total + n > max_total_decoded_bytes:
            return None, (
                f"Attachments exceed the maximum total size "
                f"({max_total_decoded_bytes // 1024} KB decoded) for one message."
            )
        total += n
        attachments.append({"media_type": mime, "data_base64": raw})

    return {"image_attachments": attachments}, None
