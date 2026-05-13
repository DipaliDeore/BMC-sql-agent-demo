from app.response_formatting import (
    build_results_narrative,
    finalize_explanation,
    merge_explanation_with_narrative,
    result_sentence_for_display,
)


def test_double_merge_does_not_repeat_scalar_narrative():
    rows = [{"COUNT(DISTINCT payment_method)": 3}]
    narrative = build_results_narrative(rows)
    assert narrative is not None

    llm = "There are 3 distinct payment methods."
    once = merge_explanation_with_narrative(llm, narrative)
    twice = merge_explanation_with_narrative(once, narrative)

    assert twice == once
    assert once.count("This value represents the overall result") == 1


def test_finalize_scalar_explanation_uses_narrative_only():
    rows = [{"COUNT(DISTINCT payment_method)": 3}]
    explanation = finalize_explanation(
        rows,
        "There are 3 distinct payment methods.\n\nThe distinct payment method is 3.",
    )

    assert explanation == build_results_narrative(rows)
    assert explanation.count("The distinct payment method is 3") == 1
    assert result_sentence_for_display(rows, None, explanation) is None
