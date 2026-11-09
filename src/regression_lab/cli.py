"""Command line entry point; replay never needs credentials or a provider SDK."""

import argparse
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
import sys

from .dataset import case_input, load_benchmark, load_fixture
from .prompts import PROMPT_ADDITIONS
from .reporting import prepare_report_paths, write_reports
from .runner import ReplayProvider, engine_hash, run_experiment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Financial LLM Regression Lab")
    subparsers = parser.add_subparsers(dest="command", required=True)
    replay = subparsers.add_parser("replay", help="Run 12 cases against synthetic offline fixtures")
    live = subparsers.add_parser("live", help="Optional authorized OpenAI execution, or a free dry run")
    for command in (replay, live):
        command.add_argument("--output-dir", type=Path, default=Path("reports"))
        command.add_argument("--report-name", default="comparison")
        command.add_argument("--fail-on-regression", action="store_true", help="Exit 1 if any comparable case regresses")
    live.add_argument("--baseline-model", required=True)
    live.add_argument("--candidate-model", required=True)
    live.add_argument("--baseline-prompt", choices=PROMPT_ADDITIONS, default="strict-v2")
    live.add_argument("--candidate-prompt", choices=PROMPT_ADDITIONS, default="explicit-v3")
    live.add_argument("--allow-paid-api", action="store_true", help="Explicitly authorize up to 24 generation requests plus bounded retries")
    preview = live.add_mutually_exclusive_group()
    preview.add_argument("--dry-run", action="store_true", help="Validate configuration and preview input hashes; no network or key")
    preview.add_argument("--preflight-only", action="store_true", help="Read-only model access check; no generation")
    live.add_argument("--env-file", type=Path, help="Explicit owner-only file containing OPENAI_API_KEY; never evaluated as shell")
    live.add_argument("--budget-usd", help="Conservative shared spending limit; requires pricing file and zero retries")
    live.add_argument("--pricing-file", type=Path, help="Reviewed dated USD prices for the requested models")
    temperature = live.add_mutually_exclusive_group()
    temperature.add_argument("--temperature", type=float, default=0.0)
    temperature.add_argument("--omit-temperature", action="store_true", help="For models that do not support temperature")
    live.add_argument("--max-output-tokens", type=int, default=2048)
    live.add_argument("--timeout", type=float, default=45.0)
    live.add_argument("--max-retries", type=int, default=1)
    live.add_argument("--reasoning-effort", choices=("none", "low", "medium", "high"),
                      help="Optional explicit effort; use only if supported by both chosen models")
    args = parser.parse_args(argv)
    try:
        snapshot, cases = load_benchmark()
        if args.command == "replay":
            baseline = ReplayProvider(load_fixture("baseline", cases))
            candidate = ReplayProvider(load_fixture("candidate", cases))
            report = run_experiment(snapshot, cases, baseline, candidate)
        else:
            from .providers import LiveConfig, OpenAIProvider, create_client, validate_models

            configs = [LiveConfig(model, prompt, None if args.omit_temperature else args.temperature,
                                  args.max_output_tokens, args.timeout, args.max_retries, args.reasoning_effort)
                       for model, prompt in [(args.baseline_model, args.baseline_prompt),
                                             (args.candidate_model, args.candidate_prompt)]]
            if configs[0] == configs[1]:
                raise ValueError("Choose different model IDs or prompt configurations")
            plan = None
            if bool(args.budget_usd) != bool(args.pricing_file):
                raise ValueError("Provide both --budget-usd and --pricing-file")
            if args.budget_usd:
                from .budget import BudgetedProvider, BudgetLedger, budget_plan, load_pricing
                plan = budget_plan(snapshot, cases, configs, load_pricing(args.pricing_file), args.budget_usd)
                if not plan["within_budget"]:
                    raise ValueError("Full planned reservations exceed the proposed budget; no network calls made")
            if args.dry_run:
                print(json.dumps({"notice": "Dry run only. No network calls; model access is unverified.",
                                  "case_count": len(cases), "generation_requests": 2 * len(cases),
                                  "engine_sha256": engine_hash(), "budget_plan": plan,
                                  "configurations": [c.describe() for c in configs],
                                  "input_sha256": {c.id: sha256(case_input(c, snapshot).encode()).hexdigest()
                                                   for c in cases}}, indent=2))
                return 0
            if args.preflight_only:
                if args.env_file:
                    from .credentials import load_key_file
                    load_key_file(args.env_file)
                with create_client(configs[0]) as client:
                    availability = validate_models(client, [c.model for c in configs])
                print(json.dumps({"notice": "Read-only account preflight; no generation calls made.",
                                  "model_availability": availability}, indent=2))
                return 0
            if not args.allow_paid_api:
                raise ValueError("No API calls made. Live execution requires --allow-paid-api; use --dry-run to preview")
            paths = prepare_report_paths(args.output_dir, args.report_name)
            if plan and any(path.exists() for path in paths):
                raise ValueError("Budgeted experiment requires a fresh report name; existing results are preserved")
            if args.env_file:
                from .credentials import load_key_file
                load_key_file(args.env_file)
            with ExitStack() as stack:
                ledger = None
                if plan:
                    journal_path = args.output_dir / (args.report_name + ".calls.jsonl")
                    journal = stack.enter_context(journal_path.open("x", encoding="utf-8"))
                    ledger = BudgetLedger(plan, journal)
                    ledger.record({"event": "plan", "budget_plan": plan,
                                   "engine_sha256": engine_hash(), "configurations": [c.describe() for c in configs]})
                client = stack.enter_context(create_client(configs[0]))
                availability = validate_models(client, [c.model for c in configs])
                baseline = OpenAIProvider(client, "baseline", configs[0], authorized=True)
                candidate = OpenAIProvider(client, "candidate", configs[1], authorized=True)
                if ledger:
                    baseline, candidate = BudgetedProvider(baseline, ledger), BudgetedProvider(candidate, ledger)
                report = run_experiment(snapshot, cases, baseline, candidate)
                if ledger:
                    report["cost_monitor"] = ledger.summary()
                    report["budget_plan"] = plan
                    report["limitations"] = [x for x in report["limitations"] if not x.startswith("No pricing configuration")]
                    report["limitations"].append("Dollar figures are estimates from reported usage and reviewed rates, not a provider invoice or hard spending cap. Unknown requests retain full reservations; the journal preserves each call.")
                    for run in report["runs"].values():
                        run["summary"]["cost_note"] = "Usage-based estimates and conservative reservations are in cost_monitor; cost_usd remains unset because no invoice was retrieved."
                report["model_availability_preflight"] = availability
                report["comparison_type"] = "prompt_configuration" if configs[0].model == configs[1].model else (
                    "model" if configs[0].prompt_id == configs[1].prompt_id else "model_and_prompt_configuration")
        paths = write_reports(report, args.output_dir, args.report_name)
    except (ValueError, OSError) as exc:
        print(f"Configuration/report error: {exc}", file=sys.stderr)
        return 2
    print(report["notice"])
    for label, run in report["runs"].items():
        s = run["summary"]
        print(f"{label}: {s['passed']}/{report['case_count']} passed; "
              f"{s['failed']} failed; {s['execution_errors']} execution errors")
    print("Regressions: " + (", ".join(report["comparison"]["regressions"]) or "none"))
    for path in paths:
        print(path.resolve())
    if report["comparison"]["not_comparable"]:
        return 2
    return 1 if args.fail_on_regression and report["comparison"]["regressions"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
