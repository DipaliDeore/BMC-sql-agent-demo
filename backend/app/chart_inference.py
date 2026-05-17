"""
When the question planner expects a chart (needs_chart) but the LLM skips
``render_chart``, infer x/y columns from the result grid so the UI still renders.
"""

from __future__ import annotations

from typing import Any

MAX_PIE_SLICES = 12
MAX_BAR_CATEGORIES = 20
MAX_LINE_POINTS = 60


def _is_numeric_like(val: Any) -> bool:
    if isinstance(val, bool) or val is None:
        return False
    if isinstance(val, (int, float)):
        return True
    if isinstance(val, str):
        s = val.strip().replace(",", "")
        if not s:
            return False
        try:
            float(s)
            return True
        except ValueError:
            return False
    return False


def _looks_like_time_dimension(key: str, sample: Any) -> bool:
    k = (key or "").lower()
    if any(x in k for x in ("date", "time", "_day", "week", "month", "year")):
        return True
    if isinstance(sample, str) and len(sample) >= 8 and sample[:4].isdigit():
        return sample[4] in "-/" or (len(sample) >= 10 and sample[4] == "-")
    return False


def _is_tabular_entity_list(rows: list[dict]) -> bool:
    """Wide entity listings (customers with email, etc.) are tables—not chart data."""
    if not rows or len(rows) < 2 or not isinstance(rows[0], dict):
        return False
    keys = [str(k).lower() for k in rows[0].keys()]
    rowish = sum(1 for k in keys if k in ("email", "phone", "first_name", "last_name", "address", "created_at", "updated_at"))
    if rowish >= 2 and len(rows) > 10:
        return True
    if len(keys) >= 4 and len(rows) > 15:
        return True
    return False


def _should_skip_chart(plan: dict[str, Any], rows: list[dict]) -> bool:
    if plan.get("intents") and "list_table" in plan.get("intents", []):
        return True
    if _is_tabular_entity_list(rows):
        return True
    hint = plan.get("chart_hint")
    if hint == "pie" and len(rows) > MAX_PIE_SLICES:
        return True
    if hint == "bar" and len(rows) > MAX_BAR_CATEGORIES:
        return True
    if hint == "line" and len(rows) > MAX_LINE_POINTS:
        return True
    return False


def infer_chart_config(plan: dict[str, Any], rows: list[dict]) -> dict[str, Any] | None:
    if not plan.get("needs_chart"):
        return None
    hint = plan.get("chart_hint")
    if hint not in ("pie", "bar", "line"):
        return None
    if not rows or not isinstance(rows[0], dict):
        return None
    if _should_skip_chart(plan, rows):
        return None
    first = rows[0]
    keys = list(first.keys())
    if len(keys) < 2:
        return None

    numeric_keys = [k for k in keys if _is_numeric_like(first.get(k))]
    non_numeric_keys = [k for k in keys if not _is_numeric_like(first.get(k))]

    if hint == "line":
        if len(rows) < 2:
            return None
        if len(non_numeric_keys) >= 1 and len(numeric_keys) >= 2:
            x_key = non_numeric_keys[0]
            for k in non_numeric_keys:
                if _looks_like_time_dimension(k, first.get(k)):
                    x_key = k
                    break
            y1, y2 = numeric_keys[0], numeric_keys[1]
            if y1 == y2:
                return None
            return {
                "chart_type": "line",
                "x_column": x_key,
                "y_column": y1,
                "y_column_2": y2,
                "is_pie_chart": False,
            }
        if len(non_numeric_keys) >= 1 and len(numeric_keys) == 1:
            x_key = non_numeric_keys[0]
            for k in non_numeric_keys:
                if _looks_like_time_dimension(k, first.get(k)):
                    x_key = k
                    break
            return {
                "chart_type": "line",
                "x_column": x_key,
                "y_column": numeric_keys[0],
                "is_pie_chart": False,
            }

    if not numeric_keys:
        return None

    measure_hints = (
        "revenue",
        "total_",
        "amount",
        "sales",
        "sum",
        "count",
        "qty",
        "quantity",
        "value",
        "price",
        "cost",
        "profit",
        "margin",
        "payment",
        "successful",
        "failed",
    )
    y_key = None
    for hint_sub in measure_hints:
        for nk in numeric_keys:
            if hint_sub in nk.lower():
                y_key = nk
                break
        if y_key:
            break
    if y_key is None:
        y_key = numeric_keys[-1]

    x_key = None
    for k in keys:
        if k == y_key:
            continue
        if not _is_numeric_like(first.get(k)):
            x_key = k
            break
    if x_key is None:
        for k in keys:
            if k != y_key:
                x_key = k
                break
    if x_key is None or x_key == y_key:
        return None

    out: dict[str, Any] = {
        "chart_type": hint,
        "x_column": x_key,
        "y_column": y_key,
        "is_pie_chart": hint == "pie",
    }
    return out


def apply_inferred_chart_from_plan(summary: dict[str, Any], plan: dict[str, Any]) -> None:
    """Mutate ``summary`` in place when the model omitted ``render_chart``."""
    if summary.get("status") != "success":
        return

    rows = summary.get("results") or []
    if _should_skip_chart(plan, rows):
        summary["chart_config"] = None
        if summary.get("is_multi"):
            for sub in summary.get("sub_responses") or []:
                sub["chart_config"] = None
        return

    if not plan.get("needs_chart"):
        return

    if summary.get("is_multi"):
        subs = summary.get("sub_responses") or []
        for sub in reversed(subs):
            if sub.get("chart_config") or sub.get("status") != "success":
                continue
            rows = sub.get("results") or []
            cfg = infer_chart_config(plan, rows)
            if cfg:
                sub["chart_config"] = cfg
                break
        return

    if summary.get("chart_config"):
        return
    rows = summary.get("results") or []
    cfg = infer_chart_config(plan, rows)
    if cfg:
        summary["chart_config"] = cfg
