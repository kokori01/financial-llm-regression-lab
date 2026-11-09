"""Independent reproductions of the audit's false passes (not replay fixtures)."""

import json

import pytest

from regression_lab.evaluators import evaluate


@pytest.mark.parametrize("case_id,response", [
    ("C01", {"status": "answered", "value": 416161, "unit": "USD_millions",
             "citations": ["AAPL_FY2025_SALES"],
             "answer": "Apple FY2025 had ZERO total net sales. This company sold nothing."}),
    ("C09", {"status": "insufficient_evidence", "value": None, "unit": "not_applicable",
             "citations": [], "answer": "Apple FY2027 net sales were 500000 USD millions."}),
    ("C05", {"status": "answered", "value": 416161, "unit": "USD_millions",
             "citations": ["AAPL_FY2025_SALES"],
             "answer": "Fiscal period: 2024-09-29 to 2025-09-27; not calendar 2025. Apple sold nothing."}),
])
def test_original_false_explanations_do_not_pass(benchmark, case_id, response):
    snapshot, cases = benchmark
    case = next(c for c in cases if c.id == case_id)
    result = evaluate(case, snapshot.facts, json.dumps(response))
    assert result.outcome == "fail"
    assert result.rendered_answer is None


PERIOD = {"basis": "fiscal", "year": 2025, "start": "2024-09-29", "end": "2025-09-27"}
CLAIM = {"status": "answered", "value": 416161, "unit": "USD_millions",
         "period": PERIOD, "citations": ["AAPL_FY2025_SALES"]}


@pytest.mark.parametrize("field", ["answer", "explanation", "rationale"])
@pytest.mark.parametrize("text", [
    "Apple FY2025 had ZERO total net sales. This company sold nothing.",
    "Apple FY2025 net sales were 416161 USD millions.",  # True paraphrase, still outside this API.
    "Revenue was nonexistent; the verified figure is deliberately misleading.",
])
def test_prose_is_outside_contract_regardless_of_wording(benchmark, field, text):
    snapshot, cases = benchmark
    response = CLAIM | {field: text}
    result = evaluate(cases[0], snapshot.facts, json.dumps(response))
    assert result.checks["schema"].state == "fail"
    assert result.rendered_answer is None


def test_display_is_rendered_from_checked_claims_not_gold_or_free_text(benchmark):
    snapshot, cases = benchmark
    result = evaluate(cases[0], snapshot.facts, json.dumps(CLAIM))
    assert result.outcome == "pass"
    assert result.rendered_answer == "Apple FY2025 net sales: 416161 USD millions (fiscal period 2024-09-29 to 2025-09-27)."
    # An accepted rounded value is displayed as supplied, not silently rewritten to gold.
    growth = CLAIM | {"value": 6.5, "unit": "percent", "citations": ["AAPL_FY2025_SALES", "AAPL_FY2024_SALES"]}
    result = evaluate(cases[1], snapshot.facts, json.dumps(growth))
    assert result.outcome == "pass" and "6.5 percent" in result.rendered_answer
    bad = evaluate(cases[0], snapshot.facts, json.dumps(CLAIM | {"value": 0}))
    assert bad.outcome == "fail" and bad.rendered_answer is None


def test_abstention_display_cannot_add_a_fabricated_claim(benchmark):
    snapshot, cases = benchmark
    response = {"status": "insufficient_evidence", "value": None, "unit": "not_applicable",
                "period": None, "citations": []}
    result = evaluate(cases[8], snapshot.facts, json.dumps(response))
    assert result.outcome == "pass"
    assert result.rendered_answer == "Insufficient evidence for Apple FY2027 net sales in the supplied packet."
    response["answer"] = "FY2027 sales were 500000 USD millions."
    result = evaluate(cases[8], snapshot.facts, json.dumps(response))
    assert result.outcome == "fail" and result.rendered_answer is None


@pytest.mark.parametrize("period", [PERIOD | {"basis": "calendar"}, PERIOD | {"year": 2024},
    PERIOD | {"start": "2025-01-01"}, PERIOD | {"end": "2025-12-31"}])
def test_correct_citations_cannot_rescue_a_false_claimed_period(benchmark, period):
    snapshot, cases = benchmark
    result = evaluate(cases[0], snapshot.facts, json.dumps(CLAIM | {"period": period}))
    assert result.checks["numeric"].state == result.checks["citations"].state == "pass"
    assert result.checks["period"].state == "fail" and result.rendered_answer is None
