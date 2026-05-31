"""
what_if_heuristics.py — Template SQL planners for common what-if scenarios (no LLM).
"""

from __future__ import annotations

import re
from typing import Any, Callable

from app.query_validator import QueryValidationError, validate_sql

Plan = dict[str, Any]
Handler = Callable[[str, str], Plan | None]


def _schema_has(schema: str, *tables: str) -> bool:
    sl = (schema or "").lower()
    return all(t.lower() in sl for t in tables)


def _pack(sql: str, summary: str, baseline: str, scenario: str) -> Plan | None:
    try:
        validate_sql(sql)
    except QueryValidationError:
        return None
    return {
        "queries": [sql],
        "scenario_summary": summary,
        "baseline_column": baseline,
        "scenario_column": scenario,
    }


def parse_multiplier(ql: str) -> float | None:
    if re.search(r"\b(double|doubled|2x|twice)\b", ql):
        return 2.0
    if re.search(r"\b(triple|tripled|3x)\b", ql):
        return 3.0
    if re.search(r"\b(halve|halved|half)\b", ql):
        return 0.5
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*%\s*(discount|off)\b", ql)
    if m:
        return 1.0 - float(m.group(1)) / 100.0
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*%\s+more\b", ql)
    if m:
        return 1.0 + float(m.group(1)) / 100.0
    m = re.search(
        r"\b(increase|decrease|drop|raise|lower|reduce|grow|decline|improve|eliminate|convert)(?:[ds]|ing|ment)?(?:\s+\w+){0,6}\s+by\s+(\d+(?:\.\d+)?)\s*%",
        ql,
    )
    if m:
        pct = float(m.group(2))
        verb = m.group(1) or ""
        if verb in ("decrease", "drop", "lower", "reduce", "decline"):
            return 1.0 - pct / 100.0
        return 1.0 + pct / 100.0
    m = re.search(r"\b(increase|decrease|reduce)\s+(?:by\s+)?(\d+(?:\.\d+)?)\s*%", ql)
    if m:
        pct = float(m.group(2))
        if m.group(1) == "increase":
            return 1.0 + pct / 100.0
        return 1.0 - pct / 100.0
    m = re.search(r"\bby\s+(\d+(?:\.\d+)?)\s*%", ql)
    if m:
        pct = float(m.group(1))
        if re.search(r"\b(increase|raise|grow|improve|more|higher|faster)\b", ql):
            return 1.0 + pct / 100.0
        if re.search(r"\b(decrease|reduce|lower|drop|decline|less|cut|slow)\b", ql):
            return 1.0 - pct / 100.0
    return None


def parse_top_n(ql: str, default: int = 5) -> int:
    m = re.search(r"\btop\s+(\d+)\s+products?\b", ql)
    if m:
        return max(1, min(int(m.group(1)), 50))
    return default


def parse_bottom_n(ql: str, default: int = 5) -> int:
    m = re.search(r"\bbottom\s+(\d+)\s+products?\b", ql)
    if m:
        return max(1, min(int(m.group(1)), 50))
    return default


def _product_sales_cte() -> str:
    return """
        product_sales AS (
            SELECT oi.product_id, SUM(oi.price_at_purchase * oi.quantity) AS sales
            FROM order_items oi
            GROUP BY oi.product_id
        )
    """.strip()


def _total_sales_expr() -> str:
    return "(SELECT SUM(sales) FROM product_sales)"


def _top_n_sales_subquery(n: int) -> str:
    return f"""
        (SELECT COALESCE(SUM(sales), 0) FROM (
            SELECT sales FROM product_sales ORDER BY sales DESC LIMIT {n}
        ) t)
    """.strip()


def _bottom_n_sales_subquery(n: int) -> str:
    return f"""
        (SELECT COALESCE(SUM(sales), 0) FROM (
            SELECT sales FROM product_sales ORDER BY sales ASC LIMIT {n}
        ) t)
    """.strip()


# ── Refunds / returns ────────────────────────────────────────────────────────


def try_refund_scenarios(ql: str, schema: str) -> Plan | None:
    if not _schema_has(schema, "refunds"):
        return None
    if not any(w in ql for w in ("return", "refund", "defective")):
        return None

    if re.search(r"\b(eliminate|eliminated|zero|no|remove all|fix defective)\b", ql) and "return" in ql:
        sql = """
SELECT
    COALESCE(SUM(refund_amount), 0) AS baseline_refund_total,
    0 AS scenario_refund_total
FROM refunds
        """.strip()
        return _pack(sql, "returns/refunds eliminated", "baseline_refund_total", "scenario_refund_total")

    mult = parse_multiplier(ql)
    if mult is not None and mult < 1.0:
        sql = f"""
SELECT
    COALESCE(SUM(refund_amount), 0) AS baseline_refund_total,
    COALESCE(SUM(refund_amount), 0) * {mult} AS scenario_refund_total
FROM refunds
        """.strip()
        pct = int(round((1 - mult) * 100))
        return _pack(sql, f"refunds reduced by ~{pct}%", "baseline_refund_total", "scenario_refund_total")
    return None


# ── Customer scenarios ───────────────────────────────────────────────────────


def try_customer_scenarios(ql: str, schema: str) -> Plan | None:
    if not _schema_has(schema, "orders", "order_items"):
        return None
    if not any(w in ql for w in ("customer", "buyer", "repeat", "one-time", "one time", "high-value", "high value")):
        return None

    base_cte = """
WITH customer_revenue AS (
    SELECT
        o.customer_id,
        COUNT(DISTINCT o.order_id) AS order_count,
        SUM(oi.price_at_purchase * oi.quantity) AS revenue
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.order_id
    GROUP BY o.customer_id
),
totals AS (
    SELECT
        COALESCE(SUM(revenue), 0) AS total_revenue,
        COALESCE(SUM(CASE WHEN order_count > 1 THEN revenue ELSE 0 END), 0) AS repeat_revenue,
        COALESCE(SUM(CASE WHEN order_count = 1 THEN revenue ELSE 0 END), 0) AS onetime_revenue
    FROM customer_revenue
)
    """.strip()

    mult = parse_multiplier(ql)
    if mult is not None and "repeat" in ql and "customer" in ql:
        sql = f"""
{base_cte}
SELECT
    total_revenue AS baseline_total_sales,
    (total_revenue - repeat_revenue) + (repeat_revenue * {mult}) AS scenario_total_sales
FROM totals
        """.strip()
        pct = int(round((mult - 1) * 100))
        return _pack(sql, f"repeat-customer revenue +{pct}%", "baseline_total_sales", "scenario_total_sales")

    m = re.search(r"\bconvert\s+(\d+(?:\.\d+)?)\s*%\s+of\s+(one[- ]time|one time)", ql)
    if m and _schema_has(schema, "orders", "order_items"):
        pct = float(m.group(1)) / 100.0
        sql = f"""
{base_cte},
repeat_stats AS (
    SELECT
        AVG(CASE WHEN order_count > 1 THEN revenue END) AS avg_repeat,
        AVG(CASE WHEN order_count = 1 THEN revenue END) AS avg_onetime
    FROM customer_revenue
)
SELECT
    t.total_revenue AS baseline_total_sales,
    t.total_revenue + t.onetime_revenue * {pct} * (
        COALESCE((SELECT avg_repeat / NULLIF(avg_onetime, 0) FROM repeat_stats), 1.2) - 1
    ) AS scenario_total_sales
FROM totals t
        """.strip()
        return _pack(
            sql,
            f"convert {int(pct * 100)}% of one-time buyers to repeat (estimated uplift)",
            "baseline_total_sales",
            "scenario_total_sales",
        )

    if mult is not None and ("high-value" in ql or "high value" in ql):
        sql = f"""
WITH customer_revenue AS (
    SELECT
        o.customer_id,
        SUM(oi.price_at_purchase * oi.quantity) AS revenue
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.order_id
    GROUP BY o.customer_id
),
ranked AS (
    SELECT revenue, NTILE(4) OVER (ORDER BY revenue DESC) AS spend_quartile
    FROM customer_revenue
)
SELECT
    (SELECT COALESCE(SUM(revenue), 0) FROM customer_revenue) AS baseline_total_sales,
    (SELECT COALESCE(SUM(CASE WHEN spend_quartile = 1 THEN revenue * {mult} ELSE revenue END), 0) FROM ranked) AS scenario_total_sales
        """.strip()
        pct = int(round((mult - 1) * 100))
        return _pack(sql, f"top-quartile customer spend +{pct}%", "baseline_total_sales", "scenario_total_sales")

    return None


# ── Product scenarios ────────────────────────────────────────────────────────


def try_product_scenarios(ql: str, schema: str) -> Plan | None:
    if not _schema_has(schema, "order_items"):
        return None

    mult = parse_multiplier(ql)

    # Stop selling low performers
    if "stop selling" in ql or ("low" in ql and "perform" in ql):
        n = parse_bottom_n(ql, 5)
        cte = _product_sales_cte()
        sql = f"""
WITH {cte}
SELECT
    {_total_sales_expr()} AS baseline_total_sales,
    {_total_sales_expr()} - {_bottom_n_sales_subquery(n)} AS scenario_total_sales
        """.strip()
        return _pack(sql, f"exclude bottom {n} low-performing products", "baseline_total_sales", "scenario_total_sales")

    # Price / discount on all products (not top-N slice)
    if mult is not None and (
        "all product" in ql
        or "discount" in ql
        or ("price" in ql and "product" in ql and "top" not in ql and "best seller" not in ql and "slow" not in ql)
    ):
        sql = f"""
SELECT
    SUM(oi.price_at_purchase * oi.quantity) AS baseline_total_sales,
    SUM(oi.price_at_purchase * oi.quantity) * {mult} AS scenario_total_sales
FROM order_items oi
        """.strip()
        if "discount" in ql:
            label = f"all products — {int(round((1 - mult) * 100))}% discount on revenue"
        elif mult > 1:
            label = f"product prices +{int(round((mult - 1) * 100))}% (quantity unchanged)"
        else:
            label = f"product prices {int(round((1 - mult) * 100))}% lower (quantity unchanged)"
        return _pack(sql, label, "baseline_total_sales", "scenario_total_sales")

    # High-selling / best sellers slice
    if mult is not None and any(p in ql for p in ("high-selling", "high selling", "best seller", "best-selling", "top seller")):
        n = parse_top_n(ql, 10)
        cte = _product_sales_cte()
        factor = mult - 1.0
        sql = f"""
WITH {cte}
SELECT
    {_total_sales_expr()} AS baseline_total_sales,
    {_total_sales_expr()} + {_top_n_sales_subquery(n)} * {factor} AS scenario_total_sales
        """.strip()
        pct = int(round((mult - 1) * 100)) if mult >= 1 else int(round((1 - mult) * 100))
        verb = f"+{pct}%" if mult >= 1 else f"-{pct}%"
        return _pack(sql, f"top {n} high-selling products revenue {verb}", "baseline_total_sales", "scenario_total_sales")

    # Slow-moving / reduce price
    if mult is not None and ("slow-moving" in ql or "slow moving" in ql or ("reduce" in ql and "price" in ql)):
        n = parse_bottom_n(ql, 10)
        cte = _product_sales_cte()
        factor = mult - 1.0
        sql = f"""
WITH {cte}
SELECT
    {_total_sales_expr()} AS baseline_total_sales,
    {_total_sales_expr()} + {_bottom_n_sales_subquery(n)} * {factor} AS scenario_total_sales
        """.strip()
        return _pack(sql, f"slow-moving (bottom {n}) product revenue ×{mult:g}", "baseline_total_sales", "scenario_total_sales")

    # Promote top N + multiplier (double etc.)
    if mult is not None and (parse_top_n(ql, 0) > 0 or "promote" in ql or ("top" in ql and "product" in ql)):
        n = parse_top_n(ql, 5)
        cte = _product_sales_cte()
        factor = mult - 1.0
        sql = f"""
WITH {cte}
SELECT
    {_total_sales_expr()} AS baseline_total_sales,
    {_total_sales_expr()} + {_top_n_sales_subquery(n)} * {factor} AS scenario_total_sales
        """.strip()
        label = f"top {n} products sales ×{mult:g} (others unchanged)"
        if "promote" in ql:
            label = f"promoted top {n} products — sales ×{mult:g}"
        return _pack(sql, label, "baseline_total_sales", "scenario_total_sales")

    return None


# ── Sales / revenue (generic) ────────────────────────────────────────────────


def try_sales_scenarios(ql: str, schema: str) -> Plan | None:
    mult = parse_multiplier(ql)
    if mult is None:
        return None
    if not any(w in ql for w in ("sales", "revenue", "delivery", "turnover", "income", "total")):
        # Default what-if with percent → total sales
        if "what if" not in ql:
            return None

    if _schema_has(schema, "order_items"):
        sql = f"""
SELECT
    SUM(oi.price_at_purchase * oi.quantity) AS baseline_total_sales,
    SUM(oi.price_at_purchase * oi.quantity) * {mult} AS scenario_total_sales
FROM order_items oi
        """.strip()
        if "delivery" in ql and mult > 1:
            label = f"faster delivery → total sales +{int(round((mult - 1) * 100))}%"
        elif mult > 1:
            label = f"total sales +{int(round((mult - 1) * 100))}%"
        else:
            label = f"total sales {int(round((1 - mult) * 100))}% lower"
        return _pack(sql, label, "baseline_total_sales", "scenario_total_sales")

    if _schema_has(schema, "payments") and "amount" in schema.lower():
        sql = f"""
SELECT
    SUM(p.amount) AS baseline_total_sales,
    SUM(p.amount) * {mult} AS scenario_total_sales
FROM payments p
WHERE p.payment_status IN ('COMPLETED', 'SUCCESS', 'Paid', 'paid', 'completed', 'success')
   OR p.payment_status IS NOT NULL
        """.strip()
        return _pack(sql, f"payment revenue ×{mult:g}", "baseline_total_sales", "scenario_total_sales")

    return None


# ── Combined scenarios (price + returns, etc.) ─────────────────────────────


def try_combined_scenarios(ql: str, schema: str) -> Plan | None:
    """Multi-lever what-if (e.g. raise prices and cut returns)."""
    if not _schema_has(schema, "order_items"):
        return None
    price_up = re.search(
        r"\b(increase|raise|higher)\s+prices?\b|\bprices?\s+(increase|rise|up)\b",
        ql,
    )
    returns_down = re.search(
        r"\b(reduce|lower|decrease|cut)\s+(returns?|refunds?)\b|\breturns?\s+(reduce|lower|decrease|down)\b",
        ql,
    )
    if not (price_up and returns_down):
        return None

    price_mult = 1.05
    m_price = re.search(r"prices?\s+(?:increase|rise|up)\s+by\s+(\d+(?:\.\d+)?)\s*%", ql)
    if not m_price:
        m_price = re.search(r"(?:increase|raise)\s+prices?\s+by\s+(\d+(?:\.\d+)?)\s*%", ql)
    if m_price:
        price_mult = 1.0 + float(m_price.group(1)) / 100.0

    refund_mult = 0.8
    m_refund = re.search(
        r"(?:reduce|lower|decrease|cut)\s+(?:returns?|refunds?)\s+by\s+(\d+(?:\.\d+)?)\s*%",
        ql,
    )
    if m_refund:
        refund_mult = 1.0 - float(m_refund.group(1)) / 100.0

    if _schema_has(schema, "refunds"):
        sql = f"""
WITH sales AS (
    SELECT COALESCE(SUM(oi.price_at_purchase * oi.quantity), 0) AS total_sales
    FROM order_items oi
),
ref AS (
    SELECT COALESCE(SUM(refund_amount), 0) AS total_refunds FROM refunds
)
SELECT
    s.total_sales AS baseline_net_revenue,
    s.total_sales * {price_mult} - r.total_refunds * {refund_mult} AS scenario_net_revenue
FROM sales s, ref r
        """.strip()
        return _pack(
            sql,
            f"prices ×{price_mult:g} and refunds ×{refund_mult:g} (net revenue)",
            "baseline_net_revenue",
            "scenario_net_revenue",
        )

    sql = f"""
SELECT
    SUM(oi.price_at_purchase * oi.quantity) AS baseline_total_sales,
    SUM(oi.price_at_purchase * oi.quantity) * {price_mult} AS scenario_total_sales
FROM order_items oi
    """.strip()
    return _pack(
        sql,
        f"prices ×{price_mult:g} (returns table unavailable)",
        "baseline_total_sales",
        "scenario_total_sales",
    )


# ── Seller / competitor (limited — no competitor table) ──────────────────────


def try_seller_scenarios(ql: str, schema: str) -> Plan | None:
    if "competitor" in ql and "match" in ql:
        if not _schema_has(schema, "seller_products", "products"):
            return None
        sql = """
SELECT
    SUM(oi.price_at_purchase * oi.quantity) AS baseline_total_sales,
    SUM(oi.price_at_purchase * oi.quantity) * 0.95 AS scenario_total_sales
FROM order_items oi
        """.strip()
        return _pack(
            sql,
            "approx. 5% price match assumption (no competitor table in DB)",
            "baseline_total_sales",
            "scenario_total_sales",
        )

    mult = parse_multiplier(ql)
    if mult is None:
        return None
    if "seller" not in ql and "best seller" not in ql:
        return None
    return try_product_scenarios(ql, schema)


# ── Operations / delivery metric (non-revenue) ─────────────────────────────


def try_delivery_metric_scenario(ql: str, schema: str) -> Plan | None:
    if not _schema_has(schema, "shipping"):
        return None
    if "delivery" not in ql and "shipping" not in ql:
        return None
    if parse_multiplier(ql) is not None and "sales" in ql:
        return None  # handled by sales scenario

    m = re.search(r"\b(\d+)\s+days?\b", ql)
    if m and ("improve" in ql or "faster" in ql or "reduce" in ql):
        days = int(m.group(1))
        sql = f"""
SELECT
    AVG(DATEDIFF(s.delivery_date, s.shipped_date)) AS baseline_avg_delivery_days,
    GREATEST(0, AVG(DATEDIFF(s.delivery_date, s.shipped_date)) - {days}) AS scenario_avg_delivery_days
FROM shipping s
WHERE s.shipped_date IS NOT NULL AND s.delivery_date IS NOT NULL
        """.strip()
        return _pack(
            sql,
            f"average delivery time −{days} days",
            "baseline_avg_delivery_days",
            "scenario_avg_delivery_days",
        )
    return None


HANDLERS: list[Handler] = [
    try_combined_scenarios,
    try_refund_scenarios,
    try_customer_scenarios,
    try_product_scenarios,
    try_seller_scenarios,
    try_delivery_metric_scenario,
    try_sales_scenarios,
]


def build_heuristic_plan(question: str, schema: str) -> Plan | None:
    ql = (question or "").lower()
    for handler in HANDLERS:
        plan = handler(ql, schema)
        if plan is not None:
            return plan
    return None
