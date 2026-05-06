from app.response_formatting import build_results_narrative


def test_single_value_has_meaning_not_raw_number_only():
    narrative = build_results_narrative([{"total_sales": 799400}])
    assert narrative is not None
    assert "total sales" in narrative.lower()
    assert "represents" in narrative.lower()
