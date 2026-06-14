"""
forecast_pipeline.py — Statistical forecasting for predict/forecast questions.

Flow: LLM plans historical time-series SQL → validate & execute → ARIMA (or linear
fallback) in Python → return actual + forecast rows with line chart.

TODO: optional Prophet backend (FORECAST_MODEL=prophet) for stronger seasonality.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

# pyrefly: ignore [missing-import]
from langchain_core.messages import HumanMessage

from app import config
from app.llm_errors import invoke_with_retry, rate_limited
from app.query_validator import QueryValidationError, validate_sql
from app.response_formatting import format_single_value
from app.serialization import make_json_serializable
from app.strategic_pipeline import (
    _execute_safe_sql,
    _extract_json_object,
    _get_strategic_llm,
)
from app.pipeline_sql_utils import (
    broaden_time_series_sql,
    forecast_sql_retry_candidates,
    time_series_status_rules,
)
from app.trend_pipeline import _metric_keys, _time_dimension_keys

FORECAST_RESPONSE_KIND = "forecast_series"

_FORECAST_MARKERS = (
    "predict",
    "forecast",
    "projection",
    "project future",
    "projected",
    "project sales",
    "project revenue",
    "estimate sales",
    "estimate revenue",
)

_FORECAST_METRIC_WORDS = (
    "sales",
    "revenue",
    "orders",
    "order",
    "demand",
    "payments",
    "customer",
    "customers",
    "return",
    "returns",
    "refund",
    "refunds",
    "inventory",
    "stock",
    "growth",
    "volume",
    "cost",
)

_ADVISORY_MARKERS = (
    "how can",
    "how do",
    "how should",
    "how to",
    "what should",
    "what can",
    "ways to",
    "recommend",
    "suggest",
    "help me",
    "what should i do",
    "where should",
    "which customers should",
    "which products should",
    "promote to maximize",
    "invest marketing",
    "target to maximize",
)


def _is_entity_ranking_question(ql: str) -> bool:
    """Which/who/top questions about entities — not aggregate time-series forecasts."""
    if re.search(
        r"\b(which|who|top|bottom|best|worst)\s+(products?|customers?|categories?|warehouses?|sellers?)\b",
        ql,
    ):
        return True
    return bool(re.search(r"\bwhich\s+\w+\s+(are|is)\s+(likely|expected)\b", ql))


def _is_forecast_question(ql: str) -> bool:
    if _is_entity_ranking_question(ql):
        return False
    if any(m in ql for m in _FORECAST_MARKERS):
        return True
    if "estimate" in ql and any(w in ql for w in _FORECAST_METRIC_WORDS):
        return True
    if re.search(r"\bq[1-4]\s+\d{4}\b", ql):
        return True
    if re.search(r"\bnext\s+\d+\s+(months?|weeks?|days?|quarters?)\b", ql):
        return True
    if re.search(r"\bnext\s+quarter\b", ql):
        return True
    if re.search(r"\b(upcoming|future)\s+\d+\s+(months?|weeks?)\b", ql):
        return True
    if re.search(r"\b(expected|projected|anticipate[ds]?)\b", ql) and any(
        w in ql for w in _FORECAST_METRIC_WORDS
    ):
        return True
    if re.search(r"\bnext\s+(month|year)\b", ql) and any(w in ql for w in _FORECAST_METRIC_WORDS):
        return True
    if re.search(r"\bwhat will\b", ql) and (
        any(w in ql for w in _FORECAST_METRIC_WORDS)
        or re.search(r"\b(next|in\s+\d+\s+months?|next\s+year)\b", ql)
    ):
        return True
    if re.search(r"\b(continues?\s+(?:growing|increasing)|current\s+(?:growth\s+)?rate)\b", ql):
        return True
    if re.search(r"\bin\s+\d+\s+months?\b", ql) and any(
        w in ql for w in ("revenue", "sales", "will be", "will look")
    ):
        return True
    if re.search(r"\bhow much\b", ql) and "expect" in ql:
        return True
    return False


def is_forecast_question(question: str) -> bool:
    return _is_forecast_question((question or "").lower())


def _is_advisory_question(ql: str) -> bool:
    return any(m in ql for m in _ADVISORY_MARKERS)


def should_use_forecast_pipeline(question: str, plan: dict[str, Any]) -> bool:
    if plan.get("strategy") in ("deterministic_sql", "what_if_mode"):
        return False

    ql = (question or "").lower()
    is_fc = "forecast" in (plan.get("intents") or []) or _is_forecast_question(ql)
    if not is_fc:
        return False
    if _is_advisory_question(ql):
        return False
    if _is_entity_ranking_question(ql):
        return False
    return True


def parse_target_quarter(question: str) -> tuple[int, int] | None:
    """Return (year, quarter_1_to_4) when the question names a calendar quarter."""
    ql = (question or "").lower()
    m = re.search(r"\bq([1-4])\s+(\d{4})\b", ql)
    if m:
        return int(m.group(2)), int(m.group(1))
    return None


def _months_to_target_quarter(last_dt: datetime, year: int, quarter: int) -> int:
    """Months from the last historical period to the end of the target quarter."""
    import pandas as pd

    target_end_month = quarter * 3
    last = pd.Timestamp(last_dt)
    target_end = pd.Timestamp(year=year, month=target_end_month, day=1)
    months = (target_end.year - last.year) * 12 + (target_end.month - last.month)
    return max(3, min(months, 36))


def parse_forecast_horizon(
    question: str,
    *,
    last_historical_dt: datetime | None = None,
) -> tuple[int, str]:
    """
    Return (horizon_count, period_unit) where period_unit is 'month' or 'week'.
    """
    ql = (question or "").lower()
    default = getattr(config, "FORECAST_DEFAULT_HORIZON", 3)

    target = parse_target_quarter(question)
    if target is not None:
        year, quarter = target
        if last_historical_dt is not None:
            return (_months_to_target_quarter(last_historical_dt, year, quarter), "month")
        return (3, "month")

    if re.search(r"\bnext\s+quarter\b", ql) or re.search(
        r"\b(?:predict|forecast|estimate).{0,20}\bquarter\b", ql
    ):
        return (3, "month")

    if re.search(r"\bnext\s+month\b", ql):
        return (1, "month")

    if re.search(r"\bnext\s+year\b", ql) or (
        re.search(r"\bannual\b", ql) and re.search(r"\bnext\b", ql)
    ):
        return (12, "month")

    m = re.search(r"\bnext\s+(\d+)\s+(months?|weeks?|days?|quarters?)\b", ql)
    if m:
        n = max(1, min(int(m.group(1)), 36))
        unit = m.group(2).rstrip("s")
        if unit == "quarter":
            return (n * 3, "month")
        if unit == "day":
            return (n, "week")
        return (n, unit)

    m = re.search(r"\bin\s+(\d+)\s+months?\b", ql)
    if m:
        return (max(1, min(int(m.group(1)), 36)), "month")

    m = re.search(r"\b(\d+)\s+(months?|weeks?)\s+(?:ahead|forward)\b", ql)
    if m:
        n = max(1, min(int(m.group(1)), 36))
        unit = m.group(2).rstrip("s")
        return (n, unit)

    m = re.search(
        r"\b(?:predict|forecast|project|estimate)\s+(?:the\s+)?(?:next\s+)?(\d+)\b", ql
    )
    if m:
        return (max(1, min(int(m.group(1)), 36)), "month")

    return (default, "month")


def _plan_forecast_sql(question: str, schema: str, references_text: str) -> str | None:
    llm = _get_strategic_llm()
    prompt = f"""Write ONE MySQL/TiDB SELECT to fetch HISTORICAL time-series data for forecasting.

Return ONLY JSON: {{"queries": ["SELECT ..."]}}

Rules:
- Exactly one query
- Historical data ONLY — do NOT include future dates or predicted values in SQL
- GROUP BY a time bucket (month preferred; week or day if the question asks for weeks/days)
- Use DATE_FORMAT / YEAR / MONTH on a date column for monthly buckets
- Include one numeric aggregate (SUM, COUNT, or AVG) for the metric in the question
- Return ALL historical periods available (no single-month filter unless the user asked)
- ORDER BY the time column ascending
- Use ONLY tables/columns from the schema
- SELECT only; LIMIT 100
{time_series_status_rules()}

Question: {question.strip()}

Schema:
{schema}

Hints:
{references_text or "None"}
"""
    response = invoke_with_retry(lambda: llm.invoke([HumanMessage(content=prompt)]))
    content = response.content
    if isinstance(content, list):
        content = " ".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    payload = _extract_json_object(str(content))
    if not payload:
        return None
    raw = payload.get("queries") or payload.get("sql") or []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        return None
    sql = str(raw[0]).strip().rstrip(";")
    if not sql:
        return None
    try:
        validate_sql(sql)
    except QueryValidationError:
        return None
    return sql


def _parse_period_label(raw: Any) -> datetime | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        import pandas as pd

        parsed = pd.to_datetime(text, errors="coerce")
        if parsed is not None and not pd.isna(parsed):
            return parsed.to_pydatetime()
    except Exception:
        pass
    return None


def _next_period_labels(last_dt: datetime, horizon: int, period: str) -> list[str]:
    import pandas as pd

    freq = "MS" if period == "month" else "W-MON"
    start = pd.Timestamp(last_dt)
    if period == "month":
        start = start + pd.DateOffset(months=1)
    else:
        start = start + pd.DateOffset(weeks=1)
    future = pd.date_range(start=start, periods=horizon, freq=freq)
    if period == "month":
        return [d.strftime("%Y-%m") for d in future]
    return [d.strftime("%Y-%m-%d") for d in future]


def _linear_forecast(values: list[float], horizon: int) -> list[float]:
    n = len(values)
    if n < 2:
        return [values[-1]] * horizon if values else [0.0] * horizon
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n)) or 1.0
    slope = num / den
    intercept = y_mean - slope * x_mean
    return [max(0.0, intercept + slope * (n + i)) for i in range(horizon)]


def _arima_forecast(values: list[float], horizon: int) -> list[float] | None:
    try:
        from statsmodels.tsa.arima.model import ARIMA

        model = ARIMA(values, order=(1, 1, 1))
        fitted = model.fit()
        preds = fitted.forecast(steps=horizon)
        return [max(0.0, float(p)) for p in preds]
    except Exception as exc:
        print(f"[ForecastPipeline] ARIMA failed, using linear fallback: {exc}")
        return None


def _run_forecast(
    rows: list[dict],
    *,
    horizon: int,
    period: str,
) -> dict[str, Any]:
    """
    Fit on historical rows and produce actual + forecast combined rows.

    Returns dict with keys: ok, rows, time_key, metric_key, forecast_col, method, message.
    """
    min_pts = getattr(config, "FORECAST_MIN_HISTORY_POINTS", 6)
    if not rows:
        return {
            "ok": False,
            "message": (
                "No historical data was returned for forecasting. "
                "If the query filtered on payment_status or order_status, the literal may not "
                "match your database (e.g. 'COMPLETED' vs 'completed'). Try again without a "
                "status filter or ask for all payments/orders."
            ),
        }

    first = rows[0] if isinstance(rows[0], dict) else {}
    time_keys = _time_dimension_keys(first)
    metric_keys = _metric_keys(first)
    time_key = time_keys[0] if time_keys else list(first.keys())[0] if first else ""
    metric_key = metric_keys[0] if metric_keys else ""

    if not time_key or not metric_key:
        return {
            "ok": False,
            "message": "Could not identify a time column and numeric metric in the query results.",
        }

    def _sort_key(row: dict) -> str:
        return str(row.get(time_key) or "")

    sorted_rows = sorted(
        [r for r in rows if isinstance(r, dict)],
        key=_sort_key,
    )

    historical: list[dict] = []
    values: list[float] = []
    for row in sorted_rows:
        if not isinstance(row, dict):
            continue
        try:
            val = float(row.get(metric_key) or 0)
        except (TypeError, ValueError):
            continue
        historical.append(row)
        values.append(val)

    n = len(values)
    if n < 3:
        return {
            "ok": False,
            "message": (
                f"Forecasting needs at least 3 historical periods; only {n} found. "
                "Try a broader date range or a different metric."
            ),
        }

    if n < min_pts:
        method = "linear_trend"
        preds = _linear_forecast(values, horizon)
    else:
        arima_preds = _arima_forecast(values, horizon)
        if arima_preds is not None:
            method = "arima"
            preds = arima_preds
        else:
            method = "linear_trend"
            preds = _linear_forecast(values, horizon)

    last_label = historical[-1].get(time_key)
    last_dt = _parse_period_label(last_label)
    if last_dt is not None:
        future_labels = _next_period_labels(last_dt, horizon, period)
    else:
        future_labels = [f"forecast_{i + 1}" for i in range(horizon)]

    forecast_col = f"{metric_key}_forecast"
    combined: list[dict] = []

    for row in historical:
        out = dict(row)
        out["is_forecast"] = False
        out["series"] = "actual"
        out[forecast_col] = None
        combined.append(out)

    if combined:
        combined[-1][forecast_col] = combined[-1].get(metric_key)

    for label, pred in zip(future_labels, preds):
        combined.append(
            {
                time_key: label,
                metric_key: None,
                forecast_col: round(pred, 2),
                "is_forecast": True,
                "series": "forecast",
            }
        )

    return {
        "ok": True,
        "rows": combined,
        "time_key": time_key,
        "metric_key": metric_key,
        "forecast_col": forecast_col,
        "method": method,
        "horizon": horizon,
        "period": period,
        "history_points": n,
    }


def _quarter_month_labels(year: int, quarter: int) -> set[str]:
    start_month = (quarter - 1) * 3 + 1
    return {f"{year}-{m:02d}" for m in range(start_month, start_month + 3)}


def _forecast_explanation(
    question: str,
    forecast_result: dict[str, Any],
) -> str:
    if not forecast_result.get("ok"):
        return forecast_result.get("message") or "Forecast could not be completed."

    method = forecast_result.get("method", "model")
    horizon = forecast_result.get("horizon", 3)
    period = forecast_result.get("period", "month")
    n = forecast_result.get("history_points", 0)
    metric_key = (forecast_result.get("metric_key") or "metric").replace("_", " ")
    method_label = "ARIMA(1,1,1)" if method == "arima" else "linear trend extrapolation"

    rows = forecast_result.get("rows") or []
    forecast_rows = [r for r in rows if r.get("is_forecast")]
    time_key = forecast_result.get("time_key") or ""
    target = parse_target_quarter(question)
    if target is not None and forecast_rows and time_key:
        year, quarter = target
        quarter_labels = _quarter_month_labels(year, quarter)
        quarter_rows = [
            r
            for r in forecast_rows
            if str(r.get(time_key) or "") in quarter_labels
        ]
        if quarter_rows:
            forecast_rows = quarter_rows

    preds: list[Any] = []
    if forecast_rows:
        fc_col = forecast_result.get("forecast_col")
        preds = [r.get(fc_col) for r in forecast_rows if fc_col]
        pred_text = ", ".join(format_single_value(p) for p in preds[:5])
        if len(preds) > 5:
            pred_text += ", …"
    else:
        pred_text = "—"

    unit = "months" if period == "month" else "weeks"
    caveat = (
        "These are statistical estimates based on past patterns, not guarantees. "
        "Use them for planning only."
    )
    if target is not None:
        year, quarter = target
        if preds:
            try:
                quarter_total = sum(float(p) for p in preds if p is not None)
                return (
                    f"Based on {n} historical {period}ly periods, a {method_label} model "
                    f"estimates Q{quarter} {year} {metric_key} at about "
                    f"{format_single_value(quarter_total)} "
                    f"(monthly breakdown: {pred_text}). {caveat}"
                )
            except (TypeError, ValueError):
                pass
        return (
            f"Based on {n} historical {period}ly periods, a {method_label} model "
            f"projects {metric_key} for Q{quarter} {year}: {pred_text}. {caveat}"
        )
    return (
        f"Based on {n} historical {period}ly periods, a {method_label} model projects "
        f"the next {horizon} {unit} of {metric_key}: {pred_text}. "
        f"{caveat}"
    )


def _forecast_chart_config(forecast_result: dict[str, Any]) -> dict[str, Any] | None:
    if not forecast_result.get("ok"):
        return None
    time_key = forecast_result.get("time_key")
    metric_key = forecast_result.get("metric_key")
    forecast_col = forecast_result.get("forecast_col")
    if not time_key or not metric_key or not forecast_col:
        return None
    return {
        "chart_type": "line",
        "x_column": time_key,
        "y_column": metric_key,
        "y_column_2": forecast_col,
        "forecast_dashed": True,
        "is_pie_chart": False,
    }


def execute_forecast_pipeline(
    question: str,
    schema: str,
    references_text: str = "",
) -> dict[str, Any] | None:
    horizon, period = parse_forecast_horizon(question)

    try:
        sql = _plan_forecast_sql(question, schema, references_text)
    except Exception as exc:
        if rate_limited(exc):
            return {
                "sql_query": "",
                "explanation": (
                    "The AI service quota has been reached. Please wait a few minutes "
                    "or try again later."
                ),
                "results": [],
                "row_count": 0,
                "status": "rate_limited",
            }
        print(f"[ForecastPipeline] SQL planning failed: {exc}")
        return None

    if not sql:
        return None

    data = _execute_safe_sql(sql)
    if not data.get("success"):
        return None

    rows = make_json_serializable(data.get("results") or [])
    if not isinstance(rows, list):
        rows = [rows]

    if not rows:
        broadened = broaden_time_series_sql(sql)
        if broadened:
            print(f"[ForecastPipeline] Retrying without status filters: {broadened[:120]}")
            data2 = _execute_safe_sql(broadened)
            if data2.get("success") and data2.get("results"):
                data = data2
                sql = broadened
                rows = make_json_serializable(data.get("results") or [])
                if not isinstance(rows, list):
                    rows = [rows]

    min_history = getattr(config, "FORECAST_MIN_HISTORY_POINTS", 6)
    if len(rows) < min_history:
        for candidate in forecast_sql_retry_candidates(sql, question, schema):
            print(
                f"[ForecastPipeline] Retrying ({len(rows)} periods < {min_history}): "
                f"{candidate[:120]}"
            )
            data_retry = _execute_safe_sql(candidate)
            if not data_retry.get("success"):
                continue
            retry_rows = make_json_serializable(data_retry.get("results") or [])
            if not isinstance(retry_rows, list):
                retry_rows = [retry_rows]
            if len(retry_rows) > len(rows):
                data = data_retry
                sql = candidate
                rows = retry_rows
                print(f"[ForecastPipeline] Using {len(rows)} historical periods")
                if len(rows) >= min_history:
                    break

    if rows and parse_target_quarter(question) is not None:
        last_label = None
        for row in reversed(rows):
            if isinstance(row, dict):
                time_keys = _time_dimension_keys(row)
                if time_keys:
                    last_label = row.get(time_keys[0])
                    break
        last_dt = _parse_period_label(last_label)
        if last_dt is not None:
            horizon, period = parse_forecast_horizon(
                question, last_historical_dt=last_dt
            )

    forecast_result = _run_forecast(rows, horizon=horizon, period=period)
    explanation = _forecast_explanation(question, forecast_result)

    if not forecast_result.get("ok"):
        return {
            "sql_query": data.get("sql") or sql,
            "explanation": explanation,
            "results": rows,
            "row_count": len(rows),
            "status": "success",
            "is_multi": False,
            "response_kind": FORECAST_RESPONSE_KIND,
            "chart_config": None,
        }

    combined = forecast_result["rows"]
    return {
        "sql_query": data.get("sql") or sql,
        "explanation": explanation,
        "results": combined,
        "row_count": len(combined),
        "status": "success",
        "is_multi": False,
        "response_kind": FORECAST_RESPONSE_KIND,
        "chart_config": _forecast_chart_config(forecast_result),
        "forecast_meta": {
            "method": forecast_result.get("method"),
            "horizon": horizon,
            "period": period,
            "history_points": forecast_result.get("history_points"),
        },
    }
