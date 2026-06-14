"""
Shared helpers for trend/forecast pipeline SQL planning and empty-result recovery.
"""

from __future__ import annotations

import re

from app.query_validator import QueryValidationError, validate_sql

_STATUS_COLS = ("payment_status", "order_status", "status")
_DATE_COLS = (
    "payment_date",
    "order_date",
    "created_at",
    "updated_at",
    "transaction_date",
    "sale_date",
)

_TIME_SERIES_STATUS_RULES = """
- Do NOT filter on payment_status, order_status, or similar enum columns unless the user explicitly asked for a status.
- Never guess status literals (e.g. 'completed' vs 'COMPLETED'). If the user did not name a status, omit status filters entirely.
- Prefer aggregating all rows with a non-null date and amount/metric column.
- Do NOT add WHERE clauses on date columns (no recent-month or current-year filters) unless the user explicitly asked for a date range.
- Return ALL historical months available in the database.
"""


def _schema_has(schema: str, table: str) -> bool:
    return table.lower() in (schema or "").lower()


def strip_date_filters(sql: str) -> str | None:
    """Remove LLM-added date range filters that shrink history to 1–2 months."""
    original = (sql or "").strip()
    if not original:
        return None

    broadened = original
    for col in _DATE_COLS:
        broadened = re.sub(
            rf"\s+AND\s+{col}\s*>=\s*'[^']*'",
            "",
            broadened,
            flags=re.IGNORECASE,
        )
        broadened = re.sub(
            rf"\s+AND\s+{col}\s*<=\s*'[^']*'",
            "",
            broadened,
            flags=re.IGNORECASE,
        )
        broadened = re.sub(
            rf"\s+AND\s+{col}\s+BETWEEN\s+'[^']*'\s+AND\s+'[^']*'",
            "",
            broadened,
            flags=re.IGNORECASE,
        )
        broadened = re.sub(
            rf"\bWHERE\s+{col}\s*>=\s*'[^']*'\s+AND\s+",
            "WHERE ",
            broadened,
            flags=re.IGNORECASE,
        )
        broadened = re.sub(
            rf"\bWHERE\s+{col}\s*BETWEEN\s+'[^']*'\s+AND\s+'[^']*'\s+AND\s+",
            "WHERE ",
            broadened,
            flags=re.IGNORECASE,
        )
        broadened = re.sub(
            rf"\bWHERE\s+{col}\s*>=\s*'[^']*'\s*(?=(GROUP|ORDER|LIMIT|HAVING)\b)",
            "",
            broadened,
            flags=re.IGNORECASE,
        )
        broadened = re.sub(
            rf"\bWHERE\s+{col}\s*BETWEEN\s+'[^']*'\s+AND\s+'[^']*'\s*(?=(GROUP|ORDER|LIMIT|HAVING)\b)",
            "",
            broadened,
            flags=re.IGNORECASE,
        )
        broadened = re.sub(
            rf"\s+AND\s+YEAR\s*\(\s*{col}\s*\)\s*=\s*\d+",
            "",
            broadened,
            flags=re.IGNORECASE,
        )

    broadened = re.sub(r"\s+", " ", broadened).strip()
    if broadened == original:
        return None
    try:
        validate_sql(broadened)
        return broadened
    except QueryValidationError:
        return None


def fallback_forecast_sql(question: str, schema: str, sql: str = "") -> str | None:
    """Deterministic monthly history when LLM SQL returns too few periods."""
    ql = (question or "").lower()
    sl = (schema or "").lower()
    sql_l = (sql or "").lower()
    forecastish = any(
        w in ql
        for w in (
            "predict",
            "forecast",
            "project",
            "estimate",
            "expected",
            "what will",
            "next ",
            "upcoming",
            "future",
        )
    ) or bool(re.search(r"\bq[1-4]\s+\d{4}\b", ql))

    use_payments = _schema_has(schema, "payments") and "payment_date" in sl and "amount" in sl
    if use_payments and (
        "payment" in ql
        or "revenue" in ql
        or "amount" in ql
        or "payments" in sql_l
        or forecastish
    ):
        return (
            "SELECT DATE_FORMAT(payment_date, '%Y-%m') AS payment_month, "
            "SUM(amount) AS total_revenue "
            "FROM payments WHERE payment_date IS NOT NULL "
            "GROUP BY payment_month ORDER BY payment_month ASC"
        )

    if any(w in ql for w in ("sales", "revenue", "order")) and _schema_has(schema, "order_items"):
        if _schema_has(schema, "orders") and "order_date" in sl:
            return (
                "SELECT DATE_FORMAT(o.order_date, '%Y-%m') AS order_month, "
                "SUM(oi.quantity * oi.price_at_purchase) AS total_sales "
                "FROM orders o "
                "JOIN order_items oi ON oi.order_id = o.order_id "
                "WHERE o.order_date IS NOT NULL "
                "GROUP BY order_month ORDER BY order_month ASC"
            )

    if "customer" in ql and _schema_has(schema, "orders") and "order_date" in sl:
        cust_col = "customer_id" if "customer_id" in sl else None
        if cust_col:
            return (
                f"SELECT DATE_FORMAT(order_date, '%Y-%m') AS order_month, "
                f"COUNT(DISTINCT {cust_col}) AS active_customers "
                f"FROM orders WHERE order_date IS NOT NULL "
                f"GROUP BY order_month ORDER BY order_month ASC"
            )

    if "return" in ql and _schema_has(schema, "returns") and "return_date" in sl:
        return (
            "SELECT DATE_FORMAT(return_date, '%Y-%m') AS return_month, "
            "COUNT(*) AS return_count "
            "FROM returns WHERE return_date IS NOT NULL "
            "GROUP BY return_month ORDER BY return_month ASC"
        )

    if (
        "refund" in ql
        and _schema_has(schema, "refunds")
        and _schema_has(schema, "returns")
        and "return_date" in sl
        and "refund_amount" in sl
    ):
        return (
            "SELECT DATE_FORMAT(r.return_date, '%Y-%m') AS refund_month, "
            "SUM(f.refund_amount) AS total_refund_cost "
            "FROM refunds f "
            "JOIN returns r ON r.return_id = f.return_id "
            "WHERE r.return_date IS NOT NULL "
            "GROUP BY refund_month ORDER BY refund_month ASC"
        )

    return None


def forecast_sql_retry_candidates(
    sql: str, question: str, schema: str
) -> list[str]:
    """Ordered SQL variants to try when history has too few monthly buckets."""
    seen: set[str] = set()
    out: list[str] = []

    def add(candidate: str | None) -> None:
        if not candidate:
            return
        c = candidate.strip()
        if not c or c in seen:
            return
        try:
            validate_sql(c)
        except QueryValidationError:
            return
        seen.add(c)
        out.append(c)

    add(strip_date_filters(sql))
    add(broaden_time_series_sql(sql))
    add(strip_date_filters(broaden_time_series_sql(sql) or ""))
    add(fallback_forecast_sql(question, schema, sql))
    return out


def time_series_status_rules() -> str:
    return _TIME_SERIES_STATUS_RULES.strip()


def broaden_time_series_sql(sql: str) -> str | None:
    """
    Drop guessed status predicates that often return zero rows (wrong enum casing).
    Returns a validated SQL string, or None if nothing changed / invalid.
    """
    original = (sql or "").strip()
    if not original:
        return None

    broadened = original
    for col in _STATUS_COLS:
        broadened = re.sub(
            rf"\s+AND\s+{col}\s*=\s*'[^']*'",
            "",
            broadened,
            flags=re.IGNORECASE,
        )
        broadened = re.sub(
            rf"\s+AND\s+{col}\s+IN\s*\([^)]+\)",
            "",
            broadened,
            flags=re.IGNORECASE,
        )
        broadened = re.sub(
            rf"\bWHERE\s+{col}\s*=\s*'[^']*'\s+AND\s+",
            "WHERE ",
            broadened,
            flags=re.IGNORECASE,
        )
        broadened = re.sub(
            rf"\bWHERE\s+{col}\s+IN\s*\([^)]+\)\s+AND\s+",
            "WHERE ",
            broadened,
            flags=re.IGNORECASE,
        )
        broadened = re.sub(
            rf"\bWHERE\s+{col}\s*=\s*'[^']*'\s*(?=(GROUP|ORDER|LIMIT|HAVING)\b)",
            "",
            broadened,
            flags=re.IGNORECASE,
        )
        broadened = re.sub(
            rf"\bWHERE\s+{col}\s+IN\s*\([^)]+\)\s*(?=(GROUP|ORDER|LIMIT|HAVING)\b)",
            "",
            broadened,
            flags=re.IGNORECASE,
        )

    broadened = re.sub(r"\s+", " ", broadened).strip()
    if broadened == original:
        return None
    try:
        validate_sql(broadened)
        return broadened
    except QueryValidationError:
        return None
