from __future__ import annotations

import re
from typing import Any


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(t in text for t in terms)


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
    if _contains_any(ql, ["by ", "each ", "per ", "month", "category", "customer", "product", "region"]):
        intents.append("breakdown")
    if _contains_any(ql, ["vs", "versus", "compare", "top ", "bottom ", "growth", "decline", "trend"]):
        intents.append("comparative_or_trend")
    if _contains_any(ql, ["increase sales", "focus on", "why did", "recommend", "improve"]):
        intents.append("strategic_recommendation")
    if _contains_any(ql, ["low stock", "warehouse", "delayed", "churn", "high demand", "frequently ordered"]):
        intents.append("operational_alert")
    if _contains_any(ql, [" and ", " also ", " along with ", ", and "]):
        intents.append("multi_intent")
    if _contains_any(ql, ["frequent", "low stock"]) and not re.search(r"\b\d+\b", ql):
        intents.append("ambiguous_thresholds")

    for ent in ("customers", "orders", "order_items", "products", "payments", "warehouse_inventory", "shipping"):
        if ent in schema.lower() and _contains_any(ql, [ent.replace("_", " "), ent]):
            entities.append(ent)

    if "strategic_recommendation" in intents:
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

    month_window = _extract_month_window(ql)
    if month_window:
        assumptions.append(
            f"Interpreting month window as month {month_window[0]} through month {month_window[1]}."
        )

    return {
        "question": q,
        "intents": intents or ["direct_metric"],
        "entities": sorted(set(entities)),
        "assumptions": assumptions,
        "strategy": strategy,
        "deterministic_sql": deterministic_sql,
    }
