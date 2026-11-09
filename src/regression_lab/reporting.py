"""Render both reports from the same executed comparison object."""

import json
from pathlib import Path
import tempfile
from typing import Any


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def markdown(report: dict[str, Any]) -> str:
    runs = report["runs"]
    candidates = {r["case_id"]: r for r in runs["candidate"]["results"]}
    pairs = [(r, candidates[r["case_id"]]) for r in sorted(runs["baseline"]["results"], key=lambda x: x["case_id"])]
    lines = ["# Financial LLM Regression Lab", "", f"**{report['notice']}**", "",
             f"Mode: `{report['mode']}`. Dataset: `{report['dataset']['dataset_id']}`.", "",
             "Comparison type: " + report.get("comparison_type", "synthetic replay configurations").replace("_", " ") + ".", "",
             report["dataset"]["description"], "",
             f"[Apple investor filing]({report['dataset']['provenance']['filing_url']}) · "
             f"[SEC filing index]({report['dataset']['provenance']['sec_index_url']})", "",
             f"Source verified: {report['dataset']['verified_on']}. "
             "Item 8, Consolidated Statements of Operations, page 29; fiscal convention in Note 1, page 34.", "",
             f"Started: {report['started_at']}. Finished: {report['finished_at']}.",
             f"{report['case_count']} cases; {report['response_attempts']} response attempts. "
             f"Measured harness runtime: {report['runtime_ms']:.3f} ms.", "",
             "## Configuration comparison", "",
             "| Label | Configuration | Executed | Pass | Fail | Execution errors |",
             "|---|---|---:|---:|---:|---:|"]
    for label, run in runs.items():
        s = run["summary"]
        lines.append(f"| {label} | {_cell(run['configuration']['id'])} | {s['executed']} | "
                     f"{s['passed']} | {s['failed']} | {s['execution_errors']} |")
    lines += ["", "Evaluation configuration:", "", "```json",
              json.dumps(report["evaluation_configuration"], indent=2), "```", ""]
    for label, run in runs.items():
        config = {k: v for k, v in run["configuration"].items() if k != "system_prompt"}
        lines += [f"{label} configuration (full prompt text retained in JSON):", "", "```json",
                  json.dumps(config, indent=2), "```", ""]
    lines += ["## Results by category", "", "Cells show pass / fail / execution error counts. "
              "Errors are excluded from evaluated-case denominators.", "",
              "| Category | Cases per configuration | Baseline | Candidate |", "|---|---:|---|---|"]
    for category, summary in runs["baseline"]["summary"]["categories"].items():
        cells = []
        for label in ("baseline", "candidate"):
            s = runs[label]["summary"]["categories"][category]
            cells.append(f"{s['passed']} / {s['failed']} / {s['execution_errors']}")
        lines.append(f"| {category} | {summary['cases']} | {' | '.join(cells)} |")
    lines += ["", "## Check results", "", "Each cell is passed/evaluated, followed by the not-evaluated count. "
              "A schema failure still fails the case; downstream checks are not given unearned passes.", "",
              "| Check | Baseline | Candidate |", "|---|---:|---:|"]
    for name in runs["baseline"]["summary"]["metrics"]:
        cells = []
        for label in ("baseline", "candidate"):
            s = runs[label]["summary"]["metrics"][name]
            cells.append(f"{s['passed']}/{s['evaluated']}; {s['not_evaluated']} not evaluated")
        lines.append(f"| {name} | {' | '.join(cells)} |")
    lines += ["", "## Paired outcomes", ""]
    for name, ids in report["comparison"].items():
        lines.append(f"- {name.replace('_', ' ').capitalize()} ({len(ids)}): {', '.join(ids) or 'none'}.")
    lines += ["", "A regression is baseline pass → candidate fail. An improvement is fail → pass. "
              "Pairs with execution errors are not comparable.", "", "| Case | Scenario | Baseline | Candidate | Candidate failed checks / error |",
              "|---|---|---|---|---|"]
    for left, right in pairs:
        failed = ", ".join(name for name, check in right["evaluation"]["checks"].items() if check["state"] == "fail")
        issue = right["execution"]["error_kind"] or failed or "none"
        lines.append(f"| {left['case_id']} | {_cell(left['title'])} | {left['evaluation']['outcome']} | "
                     f"{right['evaluation']['outcome']} | {_cell(issue)} |")
    lines += ["", "## Per-case evidence and failures", ""]
    for left, right in pairs:
        e = left["expected"]
        lines += [f"### {left['case_id']} — {left['title']}", "",
                  f"Gold: `{e['status']}`, value `{e['value']}`, unit `{e['unit']}`, "
                  f"absolute tolerance `{e['tolerance']}`. {e['derivation']}", ""]
        for label, item in (("baseline", left), ("candidate", right)):
            ev, execution = item["evaluation"], item["execution"]
            lines.append(f"- **{label}: {ev['outcome']}**")
            if ev["rendered_answer"]:
                lines.append(f"  Application-rendered answer: {_cell(ev['rendered_answer'])}")
            if execution["injected_defect"]:
                lines.append(f"  Deliberate synthetic defect: {execution['injected_defect']}")
            if execution["error_kind"]:
                lines.append(f"  Execution error ({execution['error_kind']}): {execution['error_message']}")
            for failure in ev["failures"]:
                lines.append(f"  - {_cell(failure)}")
        lines.append("")
    lines += ["## Provider errors", ""]
    for label, run in runs.items():
        s = run["summary"]
        lines.append(f"- {label}: {s['execution_errors']} execution errors; "
                     f"generation calls initiated: {s['generation_calls_initiated']}; "
                     f"error counts: {json.dumps(s['provider_error_counts'])}.")
    lines += ["", "A generation call initiated by the SDK is not proof of server receipt or billable usage. "
              "Skipped calls after configuration/quota rejection are recorded separately in execution metadata. "
              "Replay makes no generation calls.", ""]
    lines += ["## Runtime, usage and provenance", ""]
    for label, run in runs.items():
        s = run["summary"]
        usage = json.dumps(s["usage"]) if s["usage"] is not None else "unavailable"
        lines.append(f"- {label}: summed execution latency {s['latency_ms_total']:.3f} ms; "
                     f"reported usage: {usage}; invoiced cost: unavailable.")
        if run["configuration"].get("model"):
            lines.append(f"  Requested model: `{run['configuration']['model']}`. "
                         "Returned model IDs, settings, usage and timestamps are in the JSON report.")
    if report.get("cost_monitor"):
        cost = report["cost_monitor"]
        lines += ["", "### Estimated API cost and spending monitor", "",
                  f"Standard-rate estimate for calls with valid usage: **${cost['standard_rate_estimate_usd']}**. "
                  f"Conservative accounting (including any unknown-call reservations): **${cost['accounted_conservative_usd']}**. "
                  f"Proposed limit: **${cost['budget_usd']}**.", "",
                  f"All initiated calls have valid usage: `{cost['all_initiated_calls_have_valid_usage']}`. "
                  f"Monitor stopped: {_cell(cost['stop_reason'] or 'no')}.", "", cost["note"], "",
                  "This is not a provider-enforced hard cap. Requests use zero retries; the shared monitor reserves "
                  "each call before execution and checks usage afterward. Full rates and per-call accounting are in JSON.", ""]
    else:
        lines += ["", "No verified pricing configuration is provided, so no dollar cost is calculated.", ""]
    lines += ["Replay latency is local fixture access, not model inference latency. "
              "If live requests are retried, reported usage may exclude failed attempts.", "",
              f"Application: {report['application_version']}; Python: {report['environment']['python']}; "
              f"Pydantic: {report['environment']['pydantic']}.", "",
              f"Engine SHA-256: `{report['engine_sha256']}`.", ""]
    for path, checksum in report["resource_sha256"].items():
        lines.append(f"- `{path}`: `{checksum}`")
    lines += ["", "## Limitations and interpretation", ""]
    lines.extend(f"- {limitation}" for limitation in report["limitations"])
    lines += ["", "Raw responses, parsed responses, checks, failure reasons, input hashes and execution metadata "
              "are retained in the accompanying JSON report. Independent proof of concept; no affiliation with Reflexivity.", ""]
    return "\n".join(lines)


def prepare_report_paths(directory: Path, stem: str) -> tuple[Path, Path]:
    """Reject bad output destinations before an authorized run can incur cost."""
    if not stem or Path(stem).name != stem or stem in {".", ".."}:
        raise ValueError("Report name must be a plain filename stem")
    directory.mkdir(parents=True, exist_ok=True)
    md_path, json_path = directory / f"{stem}.md", directory / f"{stem}.json"
    for path in (md_path, json_path):
        if path.exists() and not path.is_file():
            raise ValueError("Report destination must be a file")
    with tempfile.TemporaryFile(dir=directory):
        pass
    return md_path, json_path


def write_reports(report: dict[str, Any], directory: Path, stem: str = "comparison") -> tuple[Path, Path]:
    md_path, json_path = prepare_report_paths(directory, stem)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    md_path.write_text(markdown(report), encoding="utf-8")
    return md_path, json_path
