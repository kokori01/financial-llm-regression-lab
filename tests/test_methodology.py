"""Independent arithmetic and adversarial mutations beyond the authored replay."""

from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
import json

import pytest

from regression_lab.dataset import calculate, validate_benchmark
from regression_lab.evaluators import evaluate

PERIOD = {"basis": "fiscal", "year": 2025, "start": "2024-09-29", "end": "2025-09-27"}
CLAIM = {"status": "answered", "value": 416161, "unit": "USD_millions", "period": PERIOD,
         "citations": ["AAPL_FY2025_SALES"]}


def test_gold_against_independent_rational_arithmetic(benchmark):
    # Filing-transcribed literals; no shared calculate() or fixture values used.
    exact = {"C02": Fraction(416161 - 391035, 391035) * 100,
             "C03": Fraction(195201, 416161) * 100,
             "C04": Fraction(133050, 416161) * 100, "C06": Fraction(416161, 1000)}
    for case in benchmark[1]:
        if case.id in exact:
            ratio = exact[case.id]
            value = (Decimal(ratio.numerator) / Decimal(ratio.denominator)).quantize(
                Decimal("0.001" if case.id == "C06" else "0.01"), rounding=ROUND_HALF_UP)
            assert Decimal(str(case.gold_value)) == value


@pytest.mark.parametrize("value", [0, -416161, 416.161, 416161000000, 416160.99])
def test_nonfixture_wrong_values_are_rejected(benchmark, value):
    result = evaluate(benchmark[1][0], benchmark[0].facts, json.dumps(CLAIM | {"value": value}))
    assert result.checks["numeric"].state == result.checks["citations"].state == "fail"
    assert result.rendered_answer is None


def test_ids_do_not_encode_success(benchmark):
    snapshot, cases = benchmark
    snapshot = snapshot.model_copy(deep=True)
    case = cases[0].model_copy(deep=True)
    snapshot.facts[0].source_id = "RENAMED_VERIFIED_RECORD"
    case.evidence_ids[0] = "RENAMED_VERIFIED_RECORD"
    case.id = "C08"
    response = CLAIM | {"citations": ["RENAMED_VERIFIED_RECORD"]}
    assert evaluate(case, snapshot.facts, json.dumps(response)).outcome == "pass"
    snapshot.facts[0].value = 416160
    assert evaluate(case, snapshot.facts, json.dumps(response)).checks["citations"].state == "fail"


def test_known_but_out_of_packet_citation_fails(benchmark):
    snapshot, cases = benchmark
    case = cases[0].model_copy(deep=True)
    case.evidence_ids.remove("AAPL_FY2025_SALES")
    result = evaluate(case, snapshot.facts, json.dumps(CLAIM))
    assert result.checks["citations"].state == "fail"
    assert "out-of-packet" in result.checks["citations"].reason


@pytest.mark.parametrize("field,value", [("gold_value", 123.0), ("expected_unit", "USD_billions")])
def test_modified_gold_fields_are_rejected_at_load(benchmark, field, value):
    snapshot, cases = benchmark
    cases = [c.model_copy(deep=True) for c in cases]
    setattr(cases[0], field, value)
    with pytest.raises(ValueError, match="gold"):
        validate_benchmark(snapshot, cases)


def test_modified_period_gold_and_accidentally_available_missing_fact(benchmark):
    snapshot, cases = benchmark
    cases = [c.model_copy(deep=True) for c in cases]
    cases[0].expected_period.start = "2025-01-01"
    with pytest.raises(ValueError, match="expected period"):
        validate_benchmark(snapshot, cases)
    snapshot, cases = benchmark
    cases = [c.model_copy(deep=True) for c in cases]
    cases[8].target_fiscal_year = 2025
    with pytest.raises(ValueError, match="missing fact is present"):
        validate_benchmark(snapshot, cases)


@pytest.mark.parametrize("operation", ["growth_percent", "ratio_percent"])
def test_invalid_denominator_is_a_benchmark_error(operation):
    with pytest.raises(ValueError, match="denominator is zero"):
        calculate(operation, [100, 0])


def test_display_target_cannot_drift_from_formula_operands(benchmark):
    snapshot, cases = benchmark
    cases = [c.model_copy(deep=True) for c in cases]
    cases[0].target_metric = "net_income"
    with pytest.raises(ValueError, match="formula operands"):
        validate_benchmark(snapshot, cases)
