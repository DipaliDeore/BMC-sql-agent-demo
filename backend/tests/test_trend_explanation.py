from app.response_formatting import build_results_narrative, finalize_explanation
from app.trend_pipeline import TREND_RESPONSE_KIND, _trend_explanation


def test_single_period_trend_explanation_is_honest():
    rows = [{"refund_month": "2026-02", "total_refund_amount": 77200}]
    text = _trend_explanation("refund amount trend over time", rows)
    assert "one time period" in text.lower()
    assert "77200" in text.replace(",", "") or "77,200" in text
    assert "trend line" in text.lower() or "no trend" in text.lower()


def test_finalize_skips_duplicate_narrative_for_trend():
    rows = [{"refund_month": "2026-02", "total_refund_amount": 77200}]
    expl = _trend_explanation("refund trend", rows)
    out = finalize_explanation(rows, expl, response_kind=TREND_RESPONSE_KIND)
    assert out == expl
    assert build_results_narrative(rows) is None
