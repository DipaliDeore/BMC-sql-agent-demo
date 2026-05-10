"""Shared helpers for building user-facing explanations from query results."""

from __future__ import annotations


def format_single_value(val) -> str:
    """Format a single value for display (no column names)."""
    if val is None:
        return "—"
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, (int, float)):
        return f"{val:,.2f}" if isinstance(val, float) else f"{val:,}"
    try:
        v = float(val)
        return f"{v:,.2f}" if v != int(v) else f"{int(v):,}"
    except (TypeError, ValueError):
        return str(val)


def _is_numeric_like(val) -> bool:
    if isinstance(val, bool) or val is None:
        return False
    if isinstance(val, (int, float)):
        return True
    try:
        float(val)
        return True
    except (TypeError, ValueError):
        return False


_RESULT_COLUMN_PHRASES: dict[str, str] = {
    "total_overall": "total sales overall",
    "total_january": "total sales in January",
    "total_february": "total sales in February",
    "total_march": "total sales in March",
    "total_amount": "total amount",
    "order_count": "number of orders",
    "customer_count": "number of customers",
}


def metric_phrase_for_column(key: str) -> str:
    """Turn a result column name into a short phrase for sentences (lowercase)."""
    raw = (key or "").strip()
    kl = raw.lower()
    if kl in _RESULT_COLUMN_PHRASES:
        return _RESULT_COLUMN_PHRASES[kl]
    label = raw
    for prefix in ("SUM(", "AVG(", "COUNT(", "MIN(", "MAX("):
        if label.upper().startswith(prefix):
            label = label[len(prefix) :]
            break
    label = label.replace(")", "").replace("(", " ").strip() or raw
    return label.replace("_", " ").strip().lower()


def build_result_sentence(results: list[dict], answer_template: str | None = None) -> str | None:
    """Return a natural language sentence ONLY when result is a single value (1 row, 1 column)."""
    if not results or len(results) != 1:
        return None
    row = results[0]
    if not row or len(row) != 1:
        return None
    key, val = next(iter(row.items()))
    formatted = format_single_value(val)
    if answer_template and "{}" in answer_template:
        try:
            return answer_template.replace("{}", formatted, 1)
        except Exception:
            pass
    return f"The {metric_phrase_for_column(key)} is {formatted}."


def build_results_narrative(results: list[dict]) -> str | None:
    """
    Human-readable summary grounded in actual cell values (for chat + LangSmith clarity).
    Single row with multiple metrics -> simple sentences; many rows -> short intro pointing to table.
    """
    if not results:
        return None
    if len(results) > 1:
        first_row = results[0] if isinstance(results[0], dict) else {}
        if len(first_row) >= 2:
            keys = list(first_row.keys())
            dim_key = keys[0]
            metric_key = keys[1]
            rows_for_breakdown = [
                r for r in results if isinstance(r, dict) and dim_key in r and metric_key in r
            ]
            if rows_for_breakdown and any(_is_numeric_like(r.get(metric_key)) for r in rows_for_breakdown):
                lines = []
                for r in rows_for_breakdown[:6]:
                    dim_val = format_single_value(r.get(dim_key))
                    metric_val = format_single_value(r.get(metric_key))
                    lines.append(f"- {dim_val}: {metric_val}")
                header = (
                    f"Here is the {metric_phrase_for_column(metric_key)} breakdown by "
                    f"{metric_phrase_for_column(dim_key)}:"
                )
                meaning = (
                    "This breakdown helps compare performance across categories in your data."
                )
                return f"{header}\n" + "\n".join(lines) + f"\n\n{meaning}"
        return (
            f"I found {len(results)} rows that match your request. "
            "The table shows the detailed breakdown."
        )

    row = results[0]
    if not row:
        return None
    if len(row) == 1:
        key, val = next(iter(row.items()))
        phrase = metric_phrase_for_column(key)
        formatted = format_single_value(val)
        return (
            f"The {phrase} is {formatted}.\n\n"
            "This value represents the overall result for the filters in your request."
        )

    sentences: list[str] = []
    for key, val in row.items():
        phrase = metric_phrase_for_column(key).capitalize()
        formatted = format_single_value(val)
        sentences.append(f"- {phrase}: {formatted}")

    body = "\n".join(sentences)
    return (
        "Here are the key values from your result:\n"
        f"{body}\n\n"
        "These numbers summarize the main metrics returned by your query."
    )


def _dedupe_adjacent_paragraphs(text: str) -> str:
    """Drop consecutive duplicate paragraphs (LLM sometimes repeats auto-narrative)."""
    parts = [p.strip() for p in (text or "").split("\n\n") if p.strip()]
    if not parts:
        return (text or "").strip()
    out: list[str] = []
    for p in parts:
        if out and out[-1] == p:
            continue
        out.append(p)
    return "\n\n".join(out)


def merge_explanation_with_narrative(llm_explanation: str, narrative: str | None) -> str:
    """Put numeric facts first; keep the model's friendly context after."""
    llm = (llm_explanation or "").strip()
    if not narrative:
        return llm
    generic_llm = llm.lower() in (
        "",
        "query executed successfully.",
        "here's what i pulled.",
        "got it!",
    )
    if generic_llm or not llm:
        return narrative
    return _dedupe_adjacent_paragraphs(f"{narrative}\n\n{llm}")
