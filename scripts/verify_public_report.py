"""Re-score public saved responses and verify provenance offline; never generates."""

from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

from regression_lab.dataset import case_input, load_benchmark
from regression_lab.evaluators import evaluate
from regression_lab.prompts import system_prompt
from regression_lab.runner import engine_hash
from regression_lab.schemas import Response


def verify(root: Path):
    report = json.loads((root / "reports/public/live_model_comparison_20261109.json").read_text())
    snapshot, cases = load_benchmark()
    assert report["engine_sha256"] == engine_hash(), "Runtime source differs from the recorded engine"
    for path, checksum in report["reproducibility"]["frozen_source_sha256"].items():
        assert sha256((root / path).read_bytes()).hexdigest() == checksum, path
    assert report["reproducibility"]["response_schema"] == Response.model_json_schema()
    expected_cases = {c.id: c for c in cases}
    total_standard = Decimal(0)
    total_conservative = Decimal(0)
    price = report["estimated_cost_usd"]["pricing"]
    outcomes = {}
    for label, run in report["runs"].items():
        config = run["configuration"]
        prompt = system_prompt(config["prompt_id"])
        assert prompt == report["reproducibility"]["system_prompt"]
        assert sha256(prompt.encode()).hexdigest() == config["system_prompt_sha256"]
        assert {r["case_id"] for r in run["results"]} == expected_cases.keys()
        assert len(run["results"]) == len(cases)
        counts = {"pass": 0, "fail": 0, "execution_error": 0}
        standard = conservative = Decimal(0)
        for row in run["results"]:
            case = expected_cases[row["case_id"]]
            assert sha256(case_input(case, snapshot).encode()).hexdigest() == row["input_sha256"]
            assert row["error_kind"] is None, "This saved experiment contains no execution errors"
            result = evaluate(case, snapshot.facts, row["raw_response"],
                              complete=row["provider_status"] == "completed", refused=row["refusal"])
            assert result.outcome == row["outcome"], row["case_id"]
            assert {k: v.state for k, v in result.checks.items()} == row["check_states"]
            assert result.failures == row["failure_reasons"]
            counts[result.outcome] += 1
            u, rates = row["usage"], price["models"][config["model"]]
            standard += (u["input_tokens"] * Decimal(rates["input_per_million"]) +
                         u["output_tokens"] * Decimal(rates["output_per_million"])) / 1000000
            conservative += (u["input_tokens"] * Decimal(rates["input_ceiling_per_million"]) +
                             u["output_tokens"] * Decimal(rates["output_per_million"])) / 1000000 * Decimal(price["safety_multiplier"])
        assert counts["pass"] == run["summary"]["passed"]
        assert counts["fail"] == run["summary"]["failed"]
        assert standard == Decimal(run["estimated_cost_usd"]["standard_rate"])
        assert conservative == Decimal(run["estimated_cost_usd"]["conservative"])
        total_standard += standard
        total_conservative += conservative
        outcomes[label] = {r["case_id"]: r["outcome"] for r in run["results"]}
    assert total_standard == Decimal(report["estimated_cost_usd"]["standard_rate"])
    assert total_conservative == Decimal(report["estimated_cost_usd"]["conservative"])
    pairs = {"regressions": [], "improvements": [], "both_fail": [], "both_pass": [], "not_comparable": []}
    names = {("pass", "fail"): "regressions", ("fail", "pass"): "improvements",
             ("pass", "pass"): "both_pass", ("fail", "fail"): "both_fail"}
    for case_id in sorted(expected_cases):
        pair = (outcomes["baseline"][case_id], outcomes["candidate"][case_id])
        pairs[names.get(pair, "not_comparable")].append(case_id)
    assert pairs == report["comparison"]
    return report


if __name__ == "__main__":
    verify(Path(__file__).resolve().parents[1])
    print("Verified 24 saved responses, input/source hashes, paired outcomes and estimated costs offline. No API calls.")
