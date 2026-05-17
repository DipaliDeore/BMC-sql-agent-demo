from app.vision_gate import (
    _build_db_grounded_explanation,
    _pick_dimension_and_metric,
    _schema_fallback_sql_candidates,
)


def test_fallback_payment_sql():
    schema = "Table: payments\nColumns: payment_id, payment_method, amount"
    candidates = _schema_fallback_sql_candidates(schema, "explain this payment chart")
    assert candidates
    assert "payment_method" in candidates[0]
    assert "COUNT" in candidates[0].upper()


def test_build_explanation_lists_all_categories():
    rows = [
        {"payment_method": "CARD", "number_of_transactions": 12},
        {"payment_method": "UPI", "number_of_transactions": 8},
        {"payment_method": "COD", "number_of_transactions": 4},
    ]
    dim, metric = _pick_dimension_and_metric(rows, "payment_method", "number_of_transactions")
    text = _build_db_grounded_explanation("explain chart", rows, dim, metric)
    assert "UPI" in text
    assert "CARD" in text
    assert "COD" in text
    assert "live data" in text.lower()
