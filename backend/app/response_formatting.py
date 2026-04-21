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
    val = next(iter(row.values()))
    formatted = format_single_value(val)
    if answer_template and "{}" in answer_template:
        try:
            return answer_template.replace("{}", formatted, 1)
        except Exception:
            pass
    return f"The result is {formatted}."


def build_results_narrative(results: list[dict]) -> str | None:
    """
    Human-readable summary grounded in actual cell values (for chat + LangSmith clarity).
    Single row with multiple metrics -> simple sentences; many rows -> short intro pointing to table.
    """
    if not results:
        return None
    if len(results) > 1:
        return f"I found {len(results)} rows — the table below has the details."

    row = results[0]
    if not row:
        return None
    if len(row) < 2:
        return None

    sentences: list[str] = []
    for key, val in row.items():
        phrase = metric_phrase_for_column(key)
        formatted = format_single_value(val)
        sentences.append(f"The {phrase} is {formatted}.")

    body = " ".join(sentences)
    return f"Here's what the data shows:\n\n{body}"


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
    return f"{narrative}\n\n{llm}"
