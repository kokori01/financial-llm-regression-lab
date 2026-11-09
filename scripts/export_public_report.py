"""Build a deterministic public extract from private saved files; no API calls."""

import argparse
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path


def select(source, fields):
    return {key: source[key] for key in fields}


def extract(report, frozen, source_digest):
    """Allowlist public fields rather than attempting to redact the whole record."""
    runs = {}
    for label in ("baseline", "candidate"):
        run = report["runs"][label]
        rows = []
        for record in run["results"]:
            execution, evaluation = record["execution"], record["evaluation"]
            rows.append(select(record, ("case_id", "title", "category", "input_sha256")) | {
                "raw_response": execution["raw_response"],
                "returned_model": execution["returned_model"],
                "usage": select(execution["usage"], ("input_tokens", "output_tokens", "total_tokens",
                                                      "cached_input_tokens", "reasoning_output_tokens")),
                "latency_ms": execution["latency_ms"],
                "provider_status": execution["provider_status"],
                "error_kind": execution["error_kind"],
                "refusal": execution["refusal"],
                "incomplete_reason": execution["incomplete_reason"],
                "effective_settings": select(execution["provider_settings"],
                                             ("temperature", "top_p", "service_tier", "reasoning")),
                "outcome": evaluation["outcome"],
                "check_states": {key: value["state"] for key, value in evaluation["checks"].items()},
                "failure_reasons": evaluation["failures"],
            })
        costs = [c for c in report["cost_monitor"]["calls"] if c["label"] == label]
        runs[label] = {
            "configuration": select(run["configuration"], (
                "model", "prompt_id", "system_prompt_sha256", "temperature", "max_output_tokens",
                "timeout_seconds", "max_retries", "interface", "store", "service_tier",
                "reasoning_effort", "output_format", "sdk_version")),
            "summary": select(run["summary"], (
                "attempted", "executed", "passed", "failed", "execution_errors", "metrics", "categories",
                "provider_error_counts", "generation_calls_initiated", "latency_ms_total", "usage")),
            "estimated_cost_usd": {
                "standard_rate": str(sum((Decimal(c["standard_rate_estimate_usd"]) for c in costs), Decimal(0))),
                "conservative": str(sum((Decimal(c["conservative_accounted_usd"]) for c in costs), Decimal(0))),
            },
            "results": rows,
        }
    return {
        "public_report_version": 1,
        "notice": "Public extract of one saved real-provider experiment; no inference was rerun for publication.",
        "omitted": ["provider response IDs", "account-access checks", "authorization records",
                    "per-call wall-clock timestamps", "private request journal", "local configuration"],
        "source_record_sha256": source_digest,
        **select(report, ("application_version", "engine_sha256", "evaluation_configuration", "environment",
                          "mode", "comparison_type", "started_at", "finished_at", "runtime_ms",
                          "dataset", "resource_sha256", "case_count", "comparison")),
        "generation_calls": report["cost_monitor"]["initiated_calls"],
        "schema_enforced_by_api": False,
        "reproducibility": {
            "system_prompt": frozen["system_prompt"],
            "response_schema": frozen["schema"],
            "frozen_source_sha256": frozen["benchmark_and_evaluator_sha256"],
            "input_reconstruction": "Use case_input(case, snapshot) from the included source. Each input hash is retained below.",
            "scope": "Saved responses can be rescored offline. Model aliases and sampling do not guarantee identical future generations.",
        },
        "estimated_cost_usd": {
            "standard_rate": report["cost_monitor"]["standard_rate_estimate_usd"],
            "conservative": report["cost_monitor"]["accounted_conservative_usd"],
            "pricing": report["cost_monitor"]["pricing"],
            "invoice_retrieved": False,
            "note": "Estimates from reported usage and rates recorded on the experiment date. Standard estimate omits cache-write premiums; conservative estimate uses higher input rates and a margin. Neither is an invoice.",
        },
        "runs": runs,
        "limitations": [
            "One filing, twelve overlapping cases, one sample per model/case, fixed baseline-first ordering.",
            "All-pass results do not establish model equivalence, statistical superiority or production reliability.",
            "Schema compliance is prompted and checked locally, not API-enforced Structured Outputs.",
            "Citation checking covers predefined evidence records and operands; general prose semantics are not evaluated.",
            "Two specified attacks do not establish broad prompt-injection resistance.",
            "Costs are estimates; exact billing and remaining account credit were not retrieved.",
        ],
    }


def markdown(report):
    runs = report["runs"]
    lines = ["# Live model comparison — 2026-11-09", "", report["notice"], "",
             f"Baseline: {runs['baseline']['summary']['passed']}/{report['case_count']}; "
             f"candidate: {runs['candidate']['summary']['passed']}/{report['case_count']}. "
             f"Regressions: {len(report['comparison']['regressions'])}; "
             f"improvements: {len(report['comparison']['improvements'])}; "
             f"provider errors: {sum(r['summary']['execution_errors'] for r in runs.values())}.", "",
             "| Measurement | Baseline | Candidate |", "|---|---:|---:|"]
    measurements = [
        ("Model", [r["configuration"]["model"] for r in runs.values()]),
        ("Passed / cases", [f"{r['summary']['passed']}/{report['case_count']}" for r in runs.values()]),
        ("Input tokens", [r["summary"]["usage"]["input_tokens"] for r in runs.values()]),
        ("Output tokens (including reasoning)", [r["summary"]["usage"]["output_tokens"] for r in runs.values()]),
        ("Standard-rate estimated USD", [r["estimated_cost_usd"]["standard_rate"] for r in runs.values()]),
        ("Conservative estimated USD", [r["estimated_cost_usd"]["conservative"] for r in runs.values()]),
        ("Summed request latency, ms", [r["summary"]["latency_ms_total"] for r in runs.values()]),
    ]
    lines.extend(f"| {name} | {values[0]} | {values[1]} |" for name, values in measurements)
    lines += ["", "## Method", "",
              "Both used the same `strict-v2` prompt, low reasoning effort, 4096 maximum output tokens, "
              "45-second timeout, zero retries, default service tier, no tools and `store=False`. "
              "Temperature was omitted. Provider settings, exact prompts and schema are retained in JSON.", "",
              "JSON/schema compliance was prompted and validated locally; it was not enforced by the API. "
              "The same twelve serialized evidence packets reached both configurations, baseline then candidate per case.", "",
              "## Cases", "", "| Case | Scenario | Baseline | Candidate |", "|---|---|---|---|"]
    right = {r["case_id"]: r for r in runs["candidate"]["results"]}
    for row in runs["baseline"]["results"]:
        lines.append(f"| {row['case_id']} | {row['title']} | {row['outcome']} | {right[row['case_id']]['outcome']} |")
    cost = report["estimated_cost_usd"]
    lines += ["", "## Cost interpretation", "",
              f"Total standard-rate estimate: **${cost['standard_rate']}**. "
              f"Conservative estimate: **${cost['conservative']}**. Neither is an exact invoice.", "",
              "Rates, verification date, input-price ceiling and margin are in the JSON and "
              "[dated pricing file](../../docs/live_pricing_2026-11-09.json). "
              "The conservative number is an accounting allowance, not measured spending.", "",
              "## Reproducibility and publication", "",
              f"Run: {report['started_at']} to {report['finished_at']}; "
              f"harness runtime {report['runtime_ms']} ms; {report['generation_calls']} generation calls.", "",
              "The [public JSON](live_model_comparison_20261109.json) retains all 24 unedited response strings, "
              "per-case checks, token usage, latency, configurations, provenance and input/source hashes. "
              "Provider response IDs, account-access checks, authorization records and private execution journals are omitted.", "",
              f"Original saved record SHA-256: `{report['source_record_sha256']}`.", "",
              "Run `python scripts/verify_public_report.py` after installation to rescore these saved responses "
              "and verify hashes without credentials or network access. "
              "The hash identifies the private source record; it is not independent provider attestation.", "",
              "## Limits", ""]
    lines.extend("- " + item for item in report["limitations"])
    lines += ["", "See [results and interpretation](../../docs/LIVE_RESULTS_20261109.md) and "
              "[methodology review](../../docs/METHODOLOGY_REVIEW.md).", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("reports/live_model_comparison_20261109.json"))
    parser.add_argument("--frozen", type=Path, default=Path("reports/live_frozen_inputs_20261109.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("reports/public"))
    args = parser.parse_args()
    report = extract(json.loads(args.source.read_text()), json.loads(args.frozen.read_text()),
                     sha256(args.source.read_bytes()).hexdigest())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.output_dir / "live_model_comparison_20261109"
    stem.with_suffix(".json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    stem.with_suffix(".md").write_text(markdown(report))
    print("Wrote public Markdown/JSON extracts; original files were read only. No API calls.")


if __name__ == "__main__":
    main()
