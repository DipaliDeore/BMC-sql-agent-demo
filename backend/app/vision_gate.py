"""
OpenAI vision: scope gate + image Q&A (charts, dashboards, SQL screenshots).
Does not call the LangGraph SQL agent — text-only queries stay on the existing path.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
from typing import Any, Protocol, runtime_checkable

from app import config
from app.database import get_database_schema

MAX_VISION_IMAGES = 4
MAX_DECODED_BYTES_PER_IMAGE = 4 * 1024 * 1024


@runtime_checkable
class _ImagePart(Protocol):
    media_type: str
    data_base64: str


_GATE_SYSTEM = """You are the relevance gate for an SQL / analytics assistant tied to ONE connected database.

You receive: the user message, the image(s), and a "Connected database schema" appendix (real tables/columns only).

Decide if the assistant should answer using vision + that schema. Prefer helping when the image is **business / analytics data** that could reasonably live in or be derived from this database.

IN SCOPE ("in_scope") — use when ANY of the following holds:

1) **Exact / text match:** Visible SQL, ERD, errors, or labels that match (or clearly substring-match) names in the appendix.

2) **Semantic / domain match (important):** The image shows charts, KPIs, tables, or dashboards about customers, orders, sales, revenue, segments, counts, regions, products, payments, or similar operational analytics — AND the appendix includes tables/columns that plausibly store or roll up that kind of data (e.g. `customers`, `orders`, `order_items`, amounts, dates, regions), even if on-screen headers use different wording (e.g. `CUSTOMER_SEGMENT`, `NUMBER_OF_CUSTOMERS`, legend text like "Frequent & High Profit") than the literal SQL column names in the appendix. In that case, treat as in_scope and briefly note the semantic link in `reason`.

3) The user names entities that appear in the appendix and the image fits that context.

OUT OF SCOPE ("out_of_scope") — use when:
- The topic is clearly unrelated to the appendix domain (memes, pets, hardware/engineering lectures, pure math, unrelated product UI with no metrics tied to the schema).
- The image is generic business art with no measurable fields, or the appendix is clearly about a different industry/domain with no plausible overlap.

UNCERTAIN ("uncertain") — rare: only if you truly cannot tell; ask ONE short clarifying question.

Do NOT require pixel-perfect equality between chart headers and SQL identifiers. **Reasonable semantic alignment** between visible metrics/dimensions and the appendix is enough for "in_scope".

Reply with ONLY a JSON object (no markdown) in this exact shape:
{"decision":"in_scope"|"out_of_scope"|"uncertain","reason":"short","clarifying_question":null or "one question"}"""


_ANSWER_SYSTEM = """You are the data and SQL copilot for this app. The image passed a relevance check against the connected database schema (including reasonable semantic alignment).

Rules:
- Ground factual claims in what is visible in the image(s). If labels or numbers are unreadable, say so.
- Do NOT claim you executed queries against the live database. Prefer **real** table/column names from the schema appendix. When chart headers use different words than SQL names (e.g. on-screen `CUSTOMER_SEGMENT`), map them to the closest appendix entities and state the mapping explicitly.
- Example SQL should use appendix names; if the image label is a display alias, write SQL using the real column(s) you infer and note the assumption.

Structure when helpful (short numbered sections):
1) What the image shows (visible metrics, dimensions, counts, segments).
2) How it relates to the connected schema — which tables/columns likely back this view, grain, and example SELECT-style questions.
3) If SQL/ERD/errors are visible — brief comment.
4) For action questions — tie to visible segments/trends and appendix; what query would validate.

Avoid unrelated domains and empty platitudes."""


def _truncate_schema(text: str, max_chars: int) -> str:
    if not text or max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20].rstrip() + "\n… [schema truncated]"


_SCHEMA_USER_PREFIX = (
    "Connected database schema (truncated for context). "
    "Use ONLY to map visible chart labels, legends, or field names to real tables/columns when there is a clear match. "
    "Do not invent table or column names. If nothing in the image matches, say so—do not fabricate SQL objects.\n\n"
)

_GATE_SCHEMA_PREFIX = (
    "Connected database schema (truncated)—these are the ONLY real tables/columns for this app.\n"
    "Gate rule: allow in_scope when chart/table labels **semantically** match what this schema can store "
    "(e.g. customer segments + counts when `customers` / `orders` style tables exist), not only on exact string matches.\n\n"
)


def _openai_client():
    if not (config.OPENAI_API_KEY or "").strip():
        return None
    from openai import OpenAI

    timeout = float(config.OPENAI_VISION_TIMEOUT_SECONDS or 60.0)
    return OpenAI(api_key=config.OPENAI_API_KEY, timeout=timeout)


def _normalize_parts(images: list[_ImagePart]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for im in images[:MAX_VISION_IMAGES]:
        mime = (im.media_type or "image/png").strip().lower()
        if mime not in ("image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"):
            mime = "image/png"
        raw = (im.data_base64 or "").strip()
        if "base64," in raw:
            raw = raw.split("base64,", 1)[-1]
        raw = re.sub(r"\s+", "", raw)
        try:
            decoded = base64.b64decode(raw, validate=True)
        except Exception as e:
            raise ValueError(f"Invalid base64 image data: {e}") from e
        if len(decoded) > MAX_DECODED_BYTES_PER_IMAGE:
            raise ValueError(
                f"Each image must be at most {MAX_DECODED_BYTES_PER_IMAGE // (1024 * 1024)} MB after decoding."
            )
        out.append((mime, raw))
    return out


def _extract_json_object(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


def _vision_message_content(
    user_text: str,
    parts: list[tuple[str, str]],
    instruction: str,
    *,
    schema_context: str | None = None,
    schema_prefix: str | None = None,
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [
        {"type": "text", "text": instruction},
        {"type": "text", "text": f"User message:\n{user_text.strip() or '(no text)'}"},
    ]
    if schema_context:
        prefix = schema_prefix if schema_prefix is not None else _SCHEMA_USER_PREFIX
        blocks.append({"type": "text", "text": prefix + schema_context})
    for mime, b64 in parts:
        blocks.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "auto"},
            }
        )
    return blocks


def _classify_sync(
    user_text: str,
    parts: list[tuple[str, str]],
    schema_context: str,
) -> dict[str, Any]:
    client = _openai_client()
    if client is None:
        return {"decision": "out_of_scope", "reason": "no_api_key", "clarifying_question": None}
    model = (config.OPENAI_VISION_MODEL or "gpt-4o-mini").strip()
    user_content = _vision_message_content(
        user_text,
        parts,
        "Classify this request.",
        schema_context=schema_context,
        schema_prefix=_GATE_SCHEMA_PREFIX,
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _GATE_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        max_tokens=500,
    )
    choice = resp.choices[0].message.content or ""
    data = _extract_json_object(choice)
    dec = (data.get("decision") or "").strip().lower()
    if dec not in ("in_scope", "out_of_scope", "uncertain"):
        dec = "uncertain"
    return {
        "decision": dec,
        "reason": str(data.get("reason") or "")[:500],
        "clarifying_question": data.get("clarifying_question"),
    }


def _answer_sync(
    user_text: str,
    parts: list[tuple[str, str]],
    schema_context: str | None = None,
) -> str:
    client = _openai_client()
    if client is None:
        return ""
    model = (config.OPENAI_VISION_MODEL or "gpt-4o-mini").strip()
    user_content = _vision_message_content(
        user_text,
        parts,
        "Answer the user.",
        schema_context=schema_context,
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _ANSWER_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        max_tokens=2500,
    )
    return (resp.choices[0].message.content or "").strip()


OUT_OF_SCOPE_MESSAGE = (
    "I can only help with images that relate to **your connected database** — including charts and metrics that "
    "match your schema by name or by obvious business meaning (e.g. customers, orders, segments). "
    "This image still looks outside that scope. Try a dashboard or query output from your app’s data, or name a table from your schema."
)

SCHEMA_UNAVAILABLE_MESSAGE = (
    "I couldn’t load your database schema, so I can’t verify whether this image relates to your data. "
    "Check that the database is reachable, then try again."
)


async def run_vision_image_pipeline(
    question: str,
    images: list[_ImagePart] | None,
    conversation_id: str,
) -> dict[str, Any] | None:
    """
    If ``images`` is non-empty, run gate + optional vision answer.
    Returns a dict suitable for ``QueryResponse`` kwargs (without assistant_message_id), or None to skip.
    """
    if not images:
        return None

    if not (config.OPENAI_API_KEY or "").strip():
        return {
            "question": question,
            "sql": "",
            "results": [],
            "explanation": (
                "Image analysis needs an OpenAI API key. Add OPENAI_API_KEY to backend/.env "
                "(optional: OPENAI_VISION_MODEL, e.g. gpt-4o-mini)."
            ),
            "row_count": 0,
            "result_sentence": None,
            "cache_references": None,
            "conversation_id": conversation_id,
            "is_ambiguous": False,
            "is_multi": False,
            "sub_responses": [],
            "cache_doc_id": None,
            "chart_config": None,
            "excel_download_url": None,
        }

    try:
        parts = _normalize_parts(images)
    except ValueError as e:
        return {
            "question": question,
            "sql": "",
            "results": [],
            "explanation": str(e),
            "row_count": 0,
            "result_sentence": None,
            "cache_references": None,
            "conversation_id": conversation_id,
            "is_ambiguous": False,
            "is_multi": False,
            "sub_responses": [],
            "cache_doc_id": None,
            "chart_config": None,
            "excel_download_url": None,
        }

    schema_text = ""
    try:
        raw_schema = await asyncio.to_thread(get_database_schema)
        schema_text = _truncate_schema(
            (raw_schema or "").strip(),
            int(getattr(config, "VISION_SCHEMA_CONTEXT_MAX_CHARS", 10000) or 10000),
        )
    except Exception as exc:
        print(f"[vision_gate] get_database_schema failed: {exc}")

    if not schema_text.strip():
        return {
            "question": question,
            "sql": "",
            "results": [],
            "explanation": SCHEMA_UNAVAILABLE_MESSAGE,
            "row_count": 0,
            "result_sentence": None,
            "cache_references": None,
            "conversation_id": conversation_id,
            "is_ambiguous": False,
            "is_multi": False,
            "sub_responses": [],
            "cache_doc_id": None,
            "chart_config": None,
            "excel_download_url": None,
        }

    gate = await asyncio.to_thread(_classify_sync, question, parts, schema_text)
    if gate.get("decision") == "out_of_scope":
        return {
            "question": question,
            "sql": "",
            "results": [],
            "explanation": OUT_OF_SCOPE_MESSAGE,
            "row_count": 0,
            "result_sentence": None,
            "cache_references": None,
            "conversation_id": conversation_id,
            "is_ambiguous": False,
            "is_multi": False,
            "sub_responses": [],
            "cache_doc_id": None,
            "chart_config": None,
            "excel_download_url": None,
        }

    if gate.get("decision") == "uncertain":
        cq = gate.get("clarifying_question")
        text = (cq if isinstance(cq, str) else None) or (
            "Which table or metric from your database does this image refer to? "
            "If you can name a column or paste a snippet that matches your schema, I can help."
        )
        return {
            "question": question,
            "sql": "",
            "results": [],
            "explanation": text.strip(),
            "row_count": 0,
            "result_sentence": None,
            "cache_references": None,
            "conversation_id": conversation_id,
            "is_ambiguous": True,
            "is_multi": False,
            "sub_responses": [],
            "cache_doc_id": None,
            "chart_config": None,
            "excel_download_url": None,
        }

    answer = await asyncio.to_thread(
        _answer_sync,
        question,
        parts,
        schema_text,
    )
    if not answer:
        answer = "I could not generate an answer from this image. Try a clearer screenshot or rephrase your question."

    return {
        "question": question,
        "sql": "",
        "results": [],
        "explanation": answer,
        "row_count": 0,
        "result_sentence": None,
        "cache_references": None,
        "conversation_id": conversation_id,
        "is_ambiguous": False,
        "is_multi": False,
        "sub_responses": [],
        "cache_doc_id": None,
        "chart_config": None,
        "excel_download_url": None,
    }
