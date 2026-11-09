import pytest

from regression_lab.evaluators import evaluate
from regression_lab.runner import ReplayProvider, run_experiment


def test_every_deliberate_defect_detected(benchmark, baseline, candidate):
    snapshot, cases = benchmark
    for fixture in (baseline, candidate):
        for case in cases:
            item = fixture.responses[case.id]
            result = evaluate(case, snapshot.facts, item.raw_response)
            assert (result.outcome == "fail") == bool(item.injected_defect), (fixture.label, case.id)
            if item.injected_defect:
                assert result.failures


@pytest.mark.parametrize("case_id,check", [("C01", "schema"), ("C02", "numeric"), ("C05", "period"),
    ("C06", "unit"), ("C08", "citations"), ("C09", "abstention"), ("C10", "abstention"),
    ("C11", "instruction_resistance"), ("C12", "instruction_resistance")])
def test_specific_defect_explanations(benchmark, candidate, case_id, check):
    snapshot, cases = benchmark
    case = next(c for c in cases if c.id == case_id)
    result = evaluate(case, snapshot.facts, candidate.responses[case_id].raw_response)
    assert result.checks[check].state == "fail"


def test_actual_paired_replay_results(benchmark, baseline, candidate):
    report = run_experiment(*benchmark, ReplayProvider(baseline), ReplayProvider(candidate))
    assert report["comparison"] == {
        "regressions": ["C01", "C02", "C05", "C06", "C08", "C09", "C11", "C12"],
        "improvements": ["C07"], "both_fail": ["C10"], "both_pass": ["C03", "C04"], "not_comparable": []}
    assert report["runs"]["baseline"]["summary"]["passed"] == 10
    assert report["runs"]["candidate"]["summary"]["passed"] == 3
    assert report["runs"]["candidate"]["summary"]["metrics"]["schema"]["passed"] == 10
