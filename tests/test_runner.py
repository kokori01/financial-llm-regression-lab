import json
import socket

import pytest

from regression_lab.cli import main
from regression_lab.comparison import compare
from regression_lab.reporting import markdown, write_reports
from regression_lab.runner import Execution, ReplayProvider, run_experiment, utc_now


def test_offline_without_credentials_or_network(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    def no_network(*args, **kwargs):
        raise AssertionError("Offline mode attempted network access")
    monkeypatch.setattr(socket.socket, "connect", no_network)
    assert main(["replay", "--output-dir", str(tmp_path)]) == 0
    report = json.loads((tmp_path / "comparison.json").read_text())
    assert "Synthetic demonstration" in report["notice"]
    assert report["case_count"] == 12 and report["response_attempts"] == 24
    for run in report["runs"].values():
        assert run["summary"]["usage"] is None and run["summary"]["cost_usd"] is None
        assert all(r["execution"]["requested_model"] is None for r in run["results"])
    assert "semantic_faithfulness | 0/0; 12 not evaluated" in (tmp_path / "comparison.md").read_text()
    assert main(["replay", "--output-dir", str(tmp_path), "--fail-on-regression"]) == 1


def test_execution_errors_never_become_regressions(benchmark, baseline, candidate):
    class TimeoutProvider(ReplayProvider):
        def execute(self, case_id, input_text):
            return Execution(None, utc_now(), 0.1, error_kind="timeout", error_message="Timed out.")
    report = run_experiment(*benchmark, ReplayProvider(baseline), TimeoutProvider(candidate))
    assert report["comparison"]["regressions"] == []
    assert len(report["comparison"]["not_comparable"]) == 12
    metrics = report["runs"]["candidate"]["summary"]["metrics"]
    assert all(s["evaluated"] == 0 for s in metrics.values())


def test_identical_inputs_and_report_roundtrip(benchmark, baseline, candidate, tmp_path):
    report = run_experiment(*benchmark, ReplayProvider(baseline), ReplayProvider(candidate))
    left, right = (report["runs"][label]["results"] for label in ("baseline", "candidate"))
    assert [r["input_sha256"] for r in left] == [r["input_sha256"] for r in right]
    md, machine = write_reports(report, tmp_path)
    assert json.loads(machine.read_text()) == report
    assert md.read_text() == markdown(report)
    for case in benchmark[1]:
        assert f"### {case.id}" in md.read_text()
    right[0]["input_sha256"] = "different"
    with pytest.raises(ValueError, match="different inputs"):
        compare(left, right)
    with pytest.raises(ValueError, match="unique case IDs"):
        compare(left, right[:-1])


def test_live_dry_run_is_offline_and_disallows_identical_configs(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    args = ["live", "--baseline-model", "unverified-placeholder", "--candidate-model", "unverified-placeholder", "--dry-run"]
    assert main(args) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["generation_requests"] == 24 and len(plan["input_sha256"]) == 12
    assert "unverified" in plan["notice"]
    assert main(args + ["--candidate-prompt", "strict-v2"]) == 2


def test_category_totals_and_reordered_results(benchmark, baseline, candidate):
    report = run_experiment(*benchmark, ReplayProvider(baseline), ReplayProvider(candidate))
    expected = {"financial_calculation": (2, 2), "data_interpretation": (0, 2),
                "source_validation": (1, 1), "missing_information": (0, 2), "instruction_resistance": (0, 2)}
    for category, (passed, failed) in expected.items():
        result = report["runs"]["candidate"]["summary"]["categories"][category]
        assert (result["passed"], result["failed"]) == (passed, failed)
        assert result["evaluated"] == result["cases"] and result["execution_errors"] == 0
    # Rendering must join on identity, not accidentally compare different rows.
    original = markdown(report)
    report["runs"]["candidate"]["results"].reverse()
    assert markdown(report) == original
    assert compare(report["runs"]["baseline"]["results"], report["runs"]["candidate"]["results"]) == report["comparison"]


def test_replay_outcomes_are_deterministic(benchmark, baseline, candidate):
    reports = [run_experiment(*benchmark, ReplayProvider(baseline), ReplayProvider(candidate)) for _ in range(2)]
    assert reports[0]["comparison"] == reports[1]["comparison"]
    for label in ("baseline", "candidate"):
        assert [r["evaluation"] for r in reports[0]["runs"][label]["results"]] == [
            r["evaluation"] for r in reports[1]["runs"][label]["results"]]


def test_report_preflight_happens_before_provider_client(monkeypatch, tmp_path):
    import regression_lab.providers as providers
    def unexpected(config):
        raise AssertionError("Should reject report path before client initialization")
    monkeypatch.setattr(providers, "create_client", unexpected)
    args = ["live", "--baseline-model", "a", "--candidate-model", "b", "--allow-paid-api",
            "--output-dir", str(tmp_path), "--report-name", "../invalid"]
    assert main(args) == 2
