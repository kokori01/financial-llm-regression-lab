"""Public evidence stays independently rescorable without private run records."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def public_record():
    return json.loads((ROOT / "reports/public/live_model_comparison_20261109.json").read_text())


def test_public_report_rescores_without_private_records():
    result = script("verify_public_report").verify(ROOT)
    assert result["generation_calls"] == 24


def test_export_omits_internal_fields_without_changing_measurements():
    public = public_record()
    source = deepcopy(public)
    source["private_api_key"] = "PRIVATE_SENTINEL"
    source["model_availability_preflight"] = {"account": "PRIVATE_SENTINEL"}
    source["authorization"] = "PRIVATE_SENTINEL"
    costs = []
    for label, run in source["runs"].items():
        run["configuration"]["local_config"] = "PRIVATE_SENTINEL"
        costs.append({"label": label, "standard_rate_estimate_usd": run["estimated_cost_usd"]["standard_rate"],
                      "conservative_accounted_usd": run["estimated_cost_usd"]["conservative"]})
        for row in run["results"]:
            row["execution"] = dict(row, provider_settings=row["effective_settings"],
                                    response_id="PRIVATE_SENTINEL", credential="PRIVATE_SENTINEL")
            row["evaluation"] = {"outcome": row["outcome"], "failures": row["failure_reasons"],
                                 "checks": {k: {"state": v} for k, v in row["check_states"].items()}}
    source["cost_monitor"] = {"calls": costs, "initiated_calls": public["generation_calls"],
                              "pricing": public["estimated_cost_usd"]["pricing"],
                              "standard_rate_estimate_usd": public["estimated_cost_usd"]["standard_rate"],
                              "accounted_conservative_usd": public["estimated_cost_usd"]["conservative"]}
    frozen = {"system_prompt": public["reproducibility"]["system_prompt"],
              "schema": public["reproducibility"]["response_schema"],
              "benchmark_and_evaluator_sha256": public["reproducibility"]["frozen_source_sha256"]}
    output = script("export_public_report").extract(source, frozen, public["source_record_sha256"])
    assert "PRIVATE_SENTINEL" not in json.dumps(output)
    assert output == public


def test_public_verifier_detects_changed_model_response(tmp_path):
    public = public_record()
    for path in public["reproducibility"]["frozen_source_sha256"]:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / path, target)
    row = public["runs"]["candidate"]["results"][0]
    response = json.loads(row["raw_response"])
    response["value"] = 0
    row["raw_response"] = json.dumps(response)
    target = tmp_path / "reports/public/live_model_comparison_20261109.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(public))
    with pytest.raises(AssertionError, match="C01"):
        script("verify_public_report").verify(tmp_path)
