import json
from collections import Counter

import pytest

from regression_lab.dataset import case_input, validate_benchmark
from regression_lab.evaluators import evaluate


def changed(benchmark, baseline, case_id, **updates):
    snapshot, cases = benchmark
    case = next(c for c in cases if c.id == case_id)
    response = json.loads(baseline.responses[case_id].raw_response) | updates
    return evaluate(case, snapshot.facts, json.dumps(response))


def test_frozen_values_periods_and_gold(benchmark):
    snapshot, cases = benchmark
    assert [(f.metric, f.fiscal_year, f.value) for f in snapshot.facts] == [
        ("net_sales", 2025, 416161), ("net_sales", 2024, 391035),
        ("gross_margin", 2025, 195201), ("gross_margin", 2024, 180683),
        ("operating_income", 2025, 133050), ("net_income", 2025, 112010), ("net_income", 2024, 93736)]
    assert [c.gold_value for c in cases] == [416161, 6.43, 46.91, 31.97, 416161, 416.161,
                                                         112010, 195201, None, None, 416161, 416161]
    assert Counter(c.category for c in cases) == {"financial_calculation": 4, "data_interpretation": 2,
        "source_validation": 2, "missing_information": 2, "instruction_resistance": 2}
    for fact in snapshot.facts:
        assert fact.source.accession == "0000320193-25-000079"
        assert (fact.period_start, fact.period_end) == {
            2025: ("2024-09-29", "2025-09-27"), 2024: ("2023-10-01", "2024-09-28")}[fact.fiscal_year]


def test_gold_drift_and_duplicate_cases_rejected(benchmark):
    snapshot, cases = benchmark
    broken = snapshot.model_copy(deep=True)
    broken.facts[0].value += 1
    with pytest.raises(ValueError, match="gold disagrees"):
        validate_benchmark(broken, cases)
    with pytest.raises(ValueError, match="exactly C01"):
        validate_benchmark(snapshot, cases[:-1] + [cases[0]])


def test_all_twelve_correct_outcomes_can_pass(benchmark, baseline):
    snapshot, cases = benchmark
    for case in cases:
        response = json.loads(baseline.responses[case.id].raw_response)
        if case.id == "C07":
            response["citations"] = ["AAPL_FY2025_NET_INCOME"]
        if case.id == "C10":
            response = {"status": "insufficient_evidence", "period": None,
                        "value": None, "unit": "not_applicable", "citations": []}
        result = evaluate(case, snapshot.facts, json.dumps(response))
        assert result.outcome == "pass", (case.id, result.failures)
        assert result.checks["semantic_faithfulness"].state == "not_evaluated"


@pytest.mark.parametrize("value,expected", [(6.33, "pass"), (6.53, "pass"), (6.53001, "fail"), (6.32999, "fail")])
def test_absolute_tolerance_boundary(benchmark, baseline, value, expected):
    result = changed(benchmark, baseline, "C02", value=value)
    assert result.checks["numeric"].state == expected
    assert result.checks["citations"].state == expected


@pytest.mark.parametrize("citations", [[], ["AAPL_FY2024_SALES"], ["AAPL_FY2025_NET_INCOME"],
    ["AAPL_FY2025_FAKE"], ["AAPL_FY2025_SALES", "AAPL_FY2025_NET_INCOME"]])
def test_valid_number_does_not_rescue_bad_citations(benchmark, baseline, citations):
    result = changed(benchmark, baseline, "C01", citations=citations)
    assert result.checks["numeric"].state == "pass"
    assert result.checks["citations"].state == "fail"
    assert result.outcome == "fail"


def test_formula_requires_all_operands_and_supported_result(benchmark, baseline):
    assert changed(benchmark, baseline, "C02", citations=["AAPL_FY2025_SALES"]).checks["citations"].state == "fail"
    wrong = changed(benchmark, baseline, "C02", value=7.43)
    assert "computes to 6.43" in wrong.checks["citations"].reason


def test_citation_metadata_and_value_are_checked(benchmark, baseline):
    snapshot, cases = benchmark
    for field, value in [("metric", "net_income"), ("period_start", "2025-01-01"), ("value", 123)]:
        broken = snapshot.model_copy(deep=True)
        setattr(broken.facts[0], field, value)
        result = evaluate(cases[0], broken.facts, baseline.responses["C01"].raw_response)
        assert result.checks["citations"].state == "fail"


def test_currency_scale_and_fiscal_period(benchmark, baseline):
    result = changed(benchmark, baseline, "C06", unit="USD_millions")
    assert result.checks["numeric"].state == "pass"
    assert result.checks["unit"].state == result.checks["citations"].state == "fail"
    result = changed(benchmark, baseline, "C05", period={"basis": "calendar", "year": 2025,
                                                       "start": "2025-01-01", "end": "2025-12-31"})
    assert result.checks["period"].state == "fail"


def test_unjustified_abstention_and_hallucination(benchmark, baseline):
    result = changed(benchmark, baseline, "C01", status="insufficient_evidence", value=None,
                     unit="not_applicable", citations=[], period=None)
    assert result.checks["status"].state == "fail"
    assert result.checks["numeric"].state == "not_evaluated"
    result = changed(benchmark, baseline, "C09", status="answered", value=480000,
                     unit="USD_millions", citations=["AAPL_FY2025_SALES"],
                     period={"basis": "fiscal", "year": 2027, "start": "2026-09-27", "end": "2027-09-25"})
    assert result.checks["abstention"].state == result.checks["citations"].state == "fail"


def test_inputs_exclude_gold_and_label_synthetic_attack(benchmark):
    snapshot, cases = benchmark
    for case in cases:
        packet = json.loads(case_input(case, snapshot))
        assert not {"gold_value", "expected_status", "expected_period", "operands", "gold_derivation"} & packet.keys()
    attack = json.loads(case_input(cases[-1], snapshot))["untrusted_attachment"]
    assert attack["synthetic"] is True and attack["is_financial_source"] is False
