"""
Ensure data questions always query the live TiDB/MySQL database.

Stale answers usually come from (1) chat / checkpoint memory, (2) semantic-cache SQL
with old date filters, or (3) the LLM reusing prior turn results — not from a
separate database copy.
"""

from __future__ import annotations

import re
from typing import Any

from app.pipeline_sql_utils import strip_date_filters

_DATE_SCOPED = re.compile(
    r"\b("
    r"20\d{2}|january|february|march|april|may|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec|"
    r"q[1-4]|last month|this month|last year|this year|yesterday|today|between"
    r")\b",
    re.I,
)

_OPEN_METRIC = re.compile(
    r"\b(?:"
    r"what(?:'s| is)?(?: the)? total\s+(?:revenue|sales|payment?s?)|"
    r"total\s+(?:revenue|sales|payment?s?)|"
    r"how much\s+(?:total\s+)?(?:revenue|sales)|"
    r"overall\s+(?:revenue|sales)"
    r")\b",
    re.I,
)

_EXPLAIN_PRIOR = re.compile(
    r"\b("
    r"explain (?:that|the|this)|what does that mean|why (?:is|was) that|"
    r"the chart above|that graph|those numbers|previous (?:answer|result)|"
    r"you (?:said|told me)|from above|in the table above"
    r")\b",
    re.I,
)

_DATA_LOOKUP = re.compile(
    r"\b("
    r"show|list|count|how many|what is|what are|what was|tell me|get me|"
    r"total|sum|average|avg|revenue|sales|payment|customer|order|product|"
    r"predict|forecast|estimate|trend|compare|top |bottom "
    r")\b",
    re.I,
)


def is_explain_prior_turn(question: str) -> bool:
    return bool(_EXPLAIN_PRIOR.search((question or "").strip()))


def is_open_total_revenue_question(question: str) -> bool:
    ql = (question or "").lower().strip()
    if not ql or _DATE_SCOPED.search(ql):
        return False
    return bool(_OPEN_METRIC.search(ql))


def needs_fresh_metric_query(question: str) -> bool:
    ql = (question or "").lower()
    if is_open_total_revenue_question(question):
        return True
    if re.search(r"\b(?:current|latest|updated|now|today)\b", ql) and re.search(
        r"\b(revenue|sales|total|count)\b", ql
    ):
        return True
    return False


def needs_live_database_query(question: str, plan: dict[str, Any] | None = None) -> bool:
    """
    True when the answer must come from a new SQL run against the live DB.
    """
    q = (question or "").strip()
    if not q:
        return False
    if is_explain_prior_turn(q):
        return False

    if needs_fresh_metric_query(q):
        return True

    intents = (plan or {}).get("intents") or []
    if any(
        i in intents
        for i in (
            "direct_metric",
            "breakdown",
            "list_table",
            "comparative_or_trend",
            "forecast",
            "operational_alert",
        )
    ):
        return True
    if (plan or {}).get("strategy") == "deterministic_sql":
        return True

    return bool(_DATA_LOOKUP.search(q))


def total_revenue_deterministic_sql(schema: str) -> str | None:
    sl = (schema or "").lower()
    if "payments" in sl and "amount" in sl:
        return "SELECT SUM(amount) AS total_revenue FROM payments WHERE amount IS NOT NULL"
    if "order_items" in sl and "price_at_purchase" in sl and "quantity" in sl:
        return (
            "SELECT SUM(quantity * price_at_purchase) AS total_revenue FROM order_items"
        )
    return None


def _sql_has_restrictive_date_filter(sql: str) -> bool:
    sql_l = (sql or "").lower()
    if not _DATE_SCOPED.search(sql_l):
        return False
    return any(
        col in sql_l
        for col in (
            "payment_date",
            "order_date",
            "created_at",
            "return_date",
            "where ",
        )
    )


def cached_sql_safe_for_replay(
    question: str,
    sql: str,
    plan: dict[str, Any] | None = None,
) -> bool:
    if not (sql or "").strip():
        return False

    if not needs_live_database_query(question, plan):
        return True

    sql_l = sql.lower()
    if is_open_total_revenue_question(question) and "order_items" in sql_l:
        return False
    if _sql_has_restrictive_date_filter(sql) and not _DATE_SCOPED.search(
        (question or "").lower()
    ):
        return False
    return True


def prefer_unfiltered_sql(sql: str) -> str:
    """Drop LLM/cache date filters so live inserts are included."""
    broadened = strip_date_filters(sql)
    return broadened if broadened else sql
