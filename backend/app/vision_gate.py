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
from app.chart_inference import infer_chart_config
from app.database import execute_query, get_database_schema, select_sql_with_row_limit
from app.query_validator import QueryValidationError, validate_sql
from app.response_formatting import format_single_value
from app.serialization import make_json_serializable

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


_ANSWER_SYSTEM = """You are the data and SQL copilot for this app. The image passed a relevance check, but a live database query could not be run.

Rules:
- Describe only what you can clearly see. For anything unclear, cropped, or missing in the image, say explicitly that you cannot read it from the screenshot alone and that the user should retry so the app can query the database.
- Do NOT invent counts for categories you cannot read.
- Map visible labels to real table/column names from the schema appendix when possible.
- Give one example SELECT the app should run (using appendix names only).

Keep the answer short."""

_SQL_PLAN_SYSTEM = """You analyze a chart/dashboard screenshot against a real database schema.

The database is the source of truth. If any label, legend item, table row, or number is missing, cropped, blurry, or cut off in the image, your SQL must still return the COMPLETE breakdown from the database (do not filter to only what you can read in the image).

Return ONLY JSON (no markdown):
{
  "sql": "SELECT ...",
  "chart_hint": "pie" | "bar" | "line" | null,
  "dimension_column": "result column for categories/labels",
  "metric_column": "result column for counts or amounts",
  "unclear_in_image": ["optional list of labels/metrics that were hard to read but included via SQL"]
}

Rules:
- Exactly ONE read-only SELECT for MySQL/TiDB
- Use ONLY tables/columns from the schema appendix
- GROUP BY the category/dimension column and aggregate the metric (COUNT/SUM/AVG as appropriate)
- Include every category the schema can produce (e.g. all payment_method values, all segments)—never omit a legend color because the screenshot cropped the table
- ORDER BY the metric descending when useful
- LIMIT 100
"""

_IMAGE_DB_RESPONSE_KIND = "image_db_grounded"


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
                "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"},
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


def _plan_sql_for_image_sync(
    user_text: str,
    parts: list[tuple[str, str]],
    schema_context: str,
) -> dict[str, Any]:
    client = _openai_client()
    if client is None:
        return {}
    model = (config.OPENAI_VISION_MODEL or "gpt-4o-mini").strip()
    user_content = _vision_message_content(
        user_text,
        parts,
        "Plan one SQL query that loads the FULL data behind this chart from the database. "
        "If any legend item, row, or value is unclear or cut off in the image, the query must still return all categories from the DB.",
        schema_context=schema_context,
        schema_prefix=_GATE_SCHEMA_PREFIX,
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SQL_PLAN_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        max_tokens=800,
    )
    return _extract_json_object((resp.choices[0].message.content or "").strip())


def _schema_fallback_sql_candidates(schema_text: str, user_text: str) -> list[str]:
    """Heuristic SELECTs to try when vision-planned SQL fails—fills gaps from the DB."""
    schema_l = (schema_text or "").lower()
    ql = (user_text or "").lower()
    out: list[str] = []

    def add(sql: str) -> None:
        s = sql.strip().rstrip(";")
        if s and s not in out:
            out.append(s)

    chartish = any(
        w in ql
        for w in (
            "chart",
            "explain",
            "image",
            "screenshot",
            "dashboard",
            "breakdown",
            "distribution",
            "pie",
            "graph",
        )
    ) or not ql.strip()

    if "payments" in schema_l and "payment_method" in schema_l:
        if chartish or any(w in ql for w in ("payment", "card", "upi", "cod", "transaction", "refund")):
            add(
                "SELECT payment_method, COUNT(payment_id) AS number_of_transactions "
                "FROM payments GROUP BY payment_method "
                "ORDER BY number_of_transactions DESC"
            )

    if "returns" in schema_l and "refunds" in schema_l:
        if chartish or any(w in ql for w in ("return", "refund")):
            if "refund_amount" in schema_l:
                add(
                    "SELECT DATE_FORMAT(r.return_date, '%Y-%m') AS period, "
                    "SUM(rf.refund_amount) AS total_refund_amount "
                    "FROM returns r JOIN refunds rf ON r.return_id = rf.return_id "
                    "GROUP BY period ORDER BY period ASC"
                )

    if "customers" in schema_l:
        if chartish or "customer" in ql or "segment" in ql:
            if "segment" in schema_l:
                add(
                    "SELECT segment, COUNT(customer_id) AS number_of_customers "
                    "FROM customers GROUP BY segment ORDER BY number_of_customers DESC"
                )
            add(
                "SELECT COUNT(customer_id) AS number_of_customers FROM customers"
            )

    if "orders" in schema_l and chartish:
        if "order_status" in schema_l:
            add(
                "SELECT order_status, COUNT(order_id) AS number_of_orders "
                "FROM orders GROUP BY order_status ORDER BY number_of_orders DESC"
            )
        if "order_date" in schema_l:
            add(
                "SELECT DATE_FORMAT(order_date, '%Y-%m') AS order_month, "
                "COUNT(order_id) AS number_of_orders "
                "FROM orders GROUP BY order_month ORDER BY order_month ASC"
            )

    if "products" in schema_l and (chartish or "product" in ql):
        add(
            "SELECT category, COUNT(product_id) AS number_of_products "
            "FROM products GROUP BY category ORDER BY number_of_products DESC"
        )

    return out[:6]


def _execute_planned_sql(sql: str) -> tuple[str, list[dict], str | None]:
    try:
        validated = validate_sql(sql.strip().rstrip(";"))
    except QueryValidationError as e:
        return "", [], str(e)

    res = execute_query(validated)
    if isinstance(res, dict) and "error" in res:
        return "", [], str(res["error"])

    rows = make_json_serializable(res if isinstance(res, list) else [res])
    if not isinstance(rows, list):
        rows = [rows]
    limited = select_sql_with_row_limit(validated)
    return limited, rows, None


def _pick_dimension_and_metric(
    rows: list[dict],
    dim_hint: str | None,
    metric_hint: str | None,
) -> tuple[str | None, str | None]:
    if not rows or not isinstance(rows[0], dict):
        return None, None
    keys = list(rows[0].keys())
    if not keys:
        return None, None

    dim_key = dim_hint if dim_hint in keys else None
    metric_key = metric_hint if metric_hint in keys else None

    if not dim_key or not metric_key:
        numeric = [k for k in keys if _is_numeric_val(rows[0].get(k))]
        non_numeric = [k for k in keys if k not in numeric]
        if not dim_key and non_numeric:
            dim_key = non_numeric[0]
        if not metric_key and numeric:
            metric_key = numeric[-1]

    return dim_key, metric_key


def _is_numeric_val(val: Any) -> bool:
    if isinstance(val, bool) or val is None:
        return False
    if isinstance(val, (int, float)):
        return True
    try:
        float(val)
        return True
    except (TypeError, ValueError):
        return False


def _build_db_grounded_explanation(
    question: str,
    rows: list[dict],
    dim_key: str,
    metric_key: str,
    unclear_in_image: list[str] | None = None,
) -> str:
    lines = [
        "I queried your connected database to answer this chart. "
        "Anything that was unclear, cropped, or missing in the image is filled in from live data below.",
        "",
    ]
    if unclear_in_image:
        gaps = [str(x).strip() for x in unclear_in_image if str(x).strip()]
        if gaps:
            lines.append(
                "Hard to read in the screenshot (resolved from DB): "
                + ", ".join(gaps[:8])
                + ("…" if len(gaps) > 8 else "")
                + "."
            )
            lines.append("")
    total_metric = 0.0
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = format_single_value(row.get(dim_key))
        val = row.get(metric_key)
        try:
            total_metric += float(val or 0)
        except (TypeError, ValueError):
            pass
        lines.append(
            f"- {label}: {format_single_value(val)} "
            f"({metric_key.replace('_', ' ')})"
        )

    if rows:
        lines.append("")
        lines.append(
            f"Total across {len(rows)} categories: {format_single_value(total_metric)} "
            f"{metric_key.replace('_', ' ')}."
        )
        lines.append("")
        lines.append(
            "The table and chart below come from this query and include every category in the database."
        )
    return "\n".join(lines).strip()


def _sql_candidates_for_image(
    question: str,
    parts: list[tuple[str, str]],
    schema_text: str,
) -> list[tuple[dict[str, Any], str]]:
    """Ordered (plan_meta, sql) pairs to execute—vision plan first, then schema fallbacks."""
    plan = _plan_sql_for_image_sync(question, parts, schema_text)
    candidates: list[tuple[dict[str, Any], str]] = []

    primary = (plan.get("sql") or "").strip().rstrip(";")
    if primary:
        candidates.append((plan, primary))

    for sql in _schema_fallback_sql_candidates(schema_text, question):
        if not any(sql == existing for _, existing in candidates):
            candidates.append((plan, sql))

    return candidates


def _try_db_grounded_image_answer(
    question: str,
    parts: list[tuple[str, str]],
    schema_text: str,
) -> dict[str, Any] | None:
    last_err: str | None = None
    for plan, sql in _sql_candidates_for_image(question, parts, schema_text):
        limited_sql, rows, err = _execute_planned_sql(sql)
        if err:
            last_err = err
            continue
        if not rows:
            last_err = "no rows"
            continue

        dim_key, metric_key = _pick_dimension_and_metric(
            rows,
            plan.get("dimension_column"),
            plan.get("metric_column"),
        )
        if not dim_key or not metric_key:
            last_err = "could not infer columns"
            continue

        chart_hint = (plan.get("chart_hint") or "pie").strip().lower()
        if chart_hint not in ("pie", "bar", "line"):
            chart_hint = "pie" if len(rows) <= 8 else "bar"

        chart_plan = {"needs_chart": True, "chart_hint": chart_hint}
        chart_config = infer_chart_config(chart_plan, rows)

        unclear = plan.get("unclear_in_image")
        if not isinstance(unclear, list):
            unclear = None

        explanation = _build_db_grounded_explanation(
            question,
            rows,
            dim_key,
            metric_key,
            unclear_in_image=unclear,
        )

        return {
            "question": question,
            "sql": limited_sql,
            "results": rows,
            "explanation": explanation,
            "row_count": len(rows),
            "result_sentence": None,
            "cache_references": None,
            "conversation_id": "",
            "is_ambiguous": False,
            "is_multi": False,
            "sub_responses": [],
            "cache_doc_id": None,
            "chart_config": chart_config,
            "excel_download_url": None,
            "response_kind": _IMAGE_DB_RESPONSE_KIND,
        }

    print(f"[vision_gate] DB grounding failed after all candidates: {last_err}")
    return None


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

    grounded = await asyncio.to_thread(
        _try_db_grounded_image_answer,
        question,
        parts,
        schema_text,
    )
    if grounded is not None:
        grounded["conversation_id"] = conversation_id
        return grounded

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
