from app.pipeline_sql_utils import (
    broaden_time_series_sql,
    fallback_forecast_sql,
    forecast_sql_retry_candidates,
    strip_date_filters,
)


def test_broaden_strips_payment_status_equals():
    sql = (
        "SELECT DATE_FORMAT(payment_date, '%Y-%m') AS payment_month, "
        "SUM(amount) AS total FROM payments "
        "WHERE payment_status = 'completed' "
        "GROUP BY payment_month ORDER BY payment_month"
    )
    broadened = broaden_time_series_sql(sql)
    assert broadened is not None
    assert "payment_status" not in broadened.lower()
    assert "SUM(amount)" in broadened


def test_broaden_no_change_without_status_filter():
    sql = (
        "SELECT DATE_FORMAT(payment_date, '%Y-%m') AS m, SUM(amount) AS t "
        "FROM payments GROUP BY m ORDER BY m"
    )
    assert broaden_time_series_sql(sql) is None


def test_strip_date_filters_removes_recent_month_predicate():
    sql = (
        "SELECT DATE_FORMAT(payment_date, '%Y-%m') AS payment_month, SUM(amount) AS total "
        "FROM payments WHERE payment_date >= '2026-02-01' "
        "GROUP BY payment_month ORDER BY payment_month"
    )
    stripped = strip_date_filters(sql)
    assert stripped is not None
    assert "payment_date >=" not in stripped.lower()
    assert "SUM(amount)" in stripped


def test_fallback_forecast_sql_for_generic_predict_question():
    schema = "Table payments: payment_date, amount"
    fb = fallback_forecast_sql("Predict the next 3 months", schema)
    assert fb is not None
    assert "payments" in fb.lower()
    assert "DATE_FORMAT" in fb


def test_forecast_retry_candidates_include_fallback():
    sql = (
        "SELECT DATE_FORMAT(payment_date, '%Y-%m') AS payment_month, SUM(amount) AS total "
        "FROM payments WHERE payment_date >= '2026-02-01' AND payment_status = 'completed' "
        "GROUP BY payment_month ORDER BY payment_month"
    )
    candidates = forecast_sql_retry_candidates(
        sql, "Predict next 3 months", "payments(payment_date, amount)"
    )
    assert len(candidates) >= 2
    assert any("payments" in c.lower() for c in candidates)
