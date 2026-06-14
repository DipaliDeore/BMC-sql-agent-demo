from __future__ import annotations

import re
from typing import Any

from app.forecast_pipeline import is_forecast_question
from app.query_freshness import (
    is_open_total_revenue_question,
    total_revenue_deterministic_sql,
)


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(t in text for t in terms)


def _is_list_or_table_request(ql: str) -> bool:
    """Raw row dumps (e.g. 'give me data of customers') should not get charts."""
    if _contains_any(
        ql,
        [
            "give me data",
            "show me data",
            "get data",
            "list all",
            "list the",
            "all records",
            "all rows",
            "table of",
            "details of",
            "data of",
            "records of",
            "show all",
            "give me all",
        ],
    ):
        return True
    if re.search(
        r"\b(show|list|get|give|fetch|display)\b.{0,40}\b(customers?|orders?|products?|payments?)\b",
        ql,
    ):
        return True
    if re.search(r"\b(customers?|orders?|products?)\s+data\b", ql):
        return True
    return False


def _wants_metric_breakdown(ql: str) -> bool:
    """True when the user asks for aggregated breakdown, not a entity listing."""
    if _contains_any(ql, ["by ", "each ", "per ", "grouped by", "breakdown", "distribution"]):
        return True
    return bool(
        re.search(r"\bby\s+(month|category|customer|product|region|day|week|year|segment)\b", ql)
    )


def _metric_breakdown_wants_bar_chart(ql: str) -> bool:
    """
    Bar chart for comparing a numeric measure across categories / products / regions.
    Covers prompts like 'revenue by category' that never say 'bar chart' explicitly.
    """
    metrics = [
        "revenue",
        "sales",
        "amount",
        "income",
        "turnover",
        "profit",
        "margin",
        "quantity",
        "units sold",
        "units ",
    ]
    if not _contains_any(ql, metrics):
        return False
    dims = [
        "by category",
        "per category",
        "by product",
        "per product",
        "by region",
        "per region",
        "by segment",
        "per segment",
        "by brand",
        "by seller",
    ]
    if _contains_any(ql, dims):
        return True
    # "revenue by ..." / "sales by ..." (dimension word may follow immediately)
    if re.search(r"\b(revenue|sales|amount|income|turnover|profit)\s+by\b", ql):
        return True
    return False


def _extract_month_window(text: str) -> tuple[int, int] | None:
    month_map = {
        "jan": 1,
        "january": 1,
        "feb": 2,
        "february": 2,
        "mar": 3,
        "march": 3,
        "apr": 4,
        "april": 4,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "aug": 8,
        "august": 8,
        "sep": 9,
        "september": 9,
        "oct": 10,
        "october": 10,
        "nov": 11,
        "november": 11,
        "dec": 12,
        "december": 12,
    }
    found = []
    for token, month in month_map.items():
        if re.search(rf"\b{re.escape(token)}\b", text):
            found.append(month)
    if len(found) >= 2:
        return (min(found), max(found))
    return None


def build_question_plan(question: str, schema: str) -> dict[str, Any]:
    q = (question or "").strip()
    ql = q.lower()
    intents: list[str] = []
    assumptions: list[str] = []
    entities: list[str] = []
    strategy = "llm_sql"
    deterministic_sql: list[str] = []

    if _contains_any(ql, ["total", "count", "average", "avg", "min", "max", "sum"]):
        intents.append("direct_metric")
    if _wants_metric_breakdown(ql):
        intents.append("breakdown")
    if _is_list_or_table_request(ql):
        intents.append("list_table")
    if _contains_any(ql, ["vs", "versus", "compare", "top ", "bottom ", "growth", "decline", "trend"]):
        intents.append("comparative_or_trend")
    strategic_phrases = [
        "increase sales",
        "increase profit",
        "increase revenue",
        "focus on",
        "why did",
        "recommend",
        "improve",
        "analyze",
        "analysis",
        "insight",
        "how to",
        "how can",
        "how do",
        "how should",
        "what should",
        "what can",
        "reduce ",
        "boost ",
        "optimize",
        "target ",
        "promote",
        "retain",
        "churn",
        "margin",
        "returns",
        "competitor",
        "pricing",
        "price competition",
        "underperform",
        "out of stock",
        "low margin",
        "most valuable",
        "likely to",
        "ways to",
    ]
    advisory_markers = (
        "how can",
        "how do",
        "how should",
        "how to",
        "what should",
        "what can",
        "ways to",
        "recommend",
        "help me",
    )
    if _contains_any(ql, strategic_phrases):
        if is_forecast_question(q) and not _contains_any(ql, advisory_markers):
            pass
        else:
            intents.append("strategic_recommendation")
    if _contains_any(ql, ["low stock", "warehouse", "delayed", "churn", "high demand", "frequently ordered"]):
        intents.append("operational_alert")
    if is_forecast_question(q):
        intents.append("forecast")

    if _contains_any(ql, [" and ", " also ", " along with ", ", and "]):
        intents.append("multi_intent")
    if _contains_any(ql, ["frequent", "low stock"]) and not re.search(r"\b\d+\b", ql):
        intents.append("ambiguous_thresholds")

    what_if_markers = (
        "what if",
        "what would happen",
        "suppose ",
        "hypothetically",
        "hypothetical",
        "simulate",
        "simulation",
        "scenario",
    )
    if _contains_any(ql, what_if_markers) or re.search(
        r"\b(increase|decrease|drop|raise|lower|reduce|grow|decline)(d|s|ing)?\s+by\s+\d+(\.\d+)?\s*%",
        ql,
    ):
        intents.append("what_if_scenario")

    for ent in ("customers", "orders", "order_items", "products", "payments", "warehouse_inventory", "shipping"):
        if ent in schema.lower() and _contains_any(ql, [ent.replace("_", " "), ent]):
            entities.append(ent)

    if "what_if_scenario" in intents:
        strategy = "what_if_mode"
        assumptions.append(
            "What-if results are simulated in SQL only; the database is not modified."
        )
    elif "forecast" in intents and not _contains_any(ql, advisory_markers):
        strategy = "llm_sql"
    elif "strategic_recommendation" in intents:
        strategy = "strategic_mode"
        assumptions.append("Recommendations are based on current historical transactional patterns.")

    low_stock_demand = _contains_any(ql, ["low stock", "warehouse"]) and _contains_any(
        ql, ["frequently ordered", "high demand", "top ordered"]
    )
    if low_stock_demand:
        strategy = "deterministic_sql"
        assumptions.append(
            "Using default thresholds: high demand = at or above average units ordered; low stock = at or below average stock."
        )
        deterministic_sql.append(
            """
            WITH demand AS (
                SELECT product_id, SUM(quantity) AS total_units_ordered
                FROM order_items
                GROUP BY product_id
            ),
            stock AS (
                SELECT product_id, SUM(stock) AS total_stock_available
                FROM warehouse_inventory
                GROUP BY product_id
            ),
            joined AS (
                SELECT
                    d.product_id,
                    d.total_units_ordered,
                    COALESCE(s.total_stock_available, 0) AS total_stock_available
                FROM demand d
                LEFT JOIN stock s ON s.product_id = d.product_id
            )
            SELECT
                p.product_id,
                p.name AS product_name,
                j.total_units_ordered,
                j.total_stock_available
            FROM joined j
            JOIN products p ON p.product_id = j.product_id
            WHERE j.total_units_ordered >= (SELECT AVG(total_units_ordered) FROM joined)
              AND j.total_stock_available <= (SELECT AVG(total_stock_available) FROM joined)
            ORDER BY j.total_units_ordered DESC, j.total_stock_available ASC
            LIMIT 20
            """.strip()
        )

    rev_sql = total_revenue_deterministic_sql(schema)
    if is_open_total_revenue_question(q) and rev_sql:
        strategy = "deterministic_sql"
        assumptions.append(
            "Total revenue uses SUM(payments.amount) from the live database (all payment rows)."
        )
        deterministic_sql.append(rev_sql)

    month_window = _extract_month_window(ql)
    if month_window:
        assumptions.append(
            f"Interpreting month window as month {month_window[0]} through month {month_window[1]}."
        )

    # Chart hint for the agent: pie (part-to-whole), bar (categories / rankings), line (time / trend).
    chart_hint: str | None = None
    if "forecast" in intents:
        chart_hint = "line"
    elif re.search(r"\bpie[\s-]*chart\b|\bpie[\s-]*graph\b|\bdonut\b", ql) or _contains_any(
        ql, ["proportion", "share of", "percentage of"]
    ):
        chart_hint = "pie"
    elif _contains_any(
        ql,
        [
            "line chart",
            "time series",
            "trend",
            "daily trend",
            "over time",
            "month over month",
            "year over year",
            "daily ",
            "weekly ",
            "by month",
            "by day",
            "by week",
            "successful vs",
            "failed vs",
            " vs failed",
            " vs successful",
        ],
    ) or ("comparative_or_trend" in intents and _contains_any(ql, ["trend", "growth", "decline"])):
        chart_hint = "line"
    elif _contains_any(
        ql,
        [
            "bar chart",
            "column chart",
            "ranking",
            "top 10",
            "top 5",
            "top 3",
            "bottom ",
            "compare ",
            " versus",
            " vs ",
        ],
    ) or _metric_breakdown_wants_bar_chart(ql):
        chart_hint = "bar"
    elif ("breakdown" in intents or _contains_any(ql, ["distribution", "breakdown"])) and (
        "list_table" not in intents
    ):
        chart_hint = "pie"

    if "list_table" in intents:
        chart_hint = None

    return {
        "question": q,
        "intents": intents or ["direct_metric"],
        "entities": sorted(set(entities)),
        "assumptions": assumptions,
        "strategy": strategy,
        "deterministic_sql": deterministic_sql,
        "chart_hint": chart_hint,
        "needs_chart": chart_hint is not None,
        # Backward compatibility for older clients reading plan JSON only
        "needs_pie_chart": chart_hint == "pie",
    }
