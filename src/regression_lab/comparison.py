"""Pair by case ID, keeping operational errors outside model regressions."""

from collections import Counter
from typing import Any


def compare(baseline: list[dict[str, Any]], candidate: list[dict[str, Any]]) -> dict[str, list[str]]:
    left = {r["case_id"]: r for r in baseline}
    right = {r["case_id"]: r for r in candidate}
    if len(left) != len(baseline) or len(right) != len(candidate) or left.keys() != right.keys():
        raise ValueError("Comparison requires identical unique case IDs")
    result: dict[str, list[str]] = {k: [] for k in
                                   ("regressions", "improvements", "both_fail", "both_pass", "not_comparable")}
    categories = {("pass", "fail"): "regressions", ("fail", "pass"): "improvements",
                  ("fail", "fail"): "both_fail", ("pass", "pass"): "both_pass"}
    for case_id in sorted(left):
        if left[case_id]["input_sha256"] != right[case_id]["input_sha256"]:
            raise ValueError(f"{case_id}: cannot compare different inputs")
        pair = (left[case_id]["evaluation"]["outcome"], right[case_id]["evaluation"]["outcome"])
        result[categories.get(pair, "not_comparable")].append(case_id)
    return result


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        raise ValueError("Cannot summarize an empty run")
    outcomes = Counter(r["evaluation"]["outcome"] for r in results)
    categories = {}
    for category in sorted({r["category"] for r in results}):
        members = [r for r in results if r["category"] == category]
        counts = Counter(r["evaluation"]["outcome"] for r in members)
        categories[category] = {"cases": len(members), "evaluated": counts["pass"] + counts["fail"],
                                "passed": counts["pass"], "failed": counts["fail"],
                                "execution_errors": counts["execution_error"]}
    metrics = {}
    for name in results[0]["evaluation"]["checks"]:
        states = Counter(r["evaluation"]["checks"][name]["state"] for r in results)
        evaluated = states["pass"] + states["fail"]
        metrics[name] = {"passed": states["pass"], "failed": states["fail"],
                         "not_evaluated": states["not_evaluated"], "evaluated": evaluated,
                         "pass_rate": states["pass"] / evaluated if evaluated else None}
    usages = [r["execution"]["usage"] for r in results if r["execution"]["usage"] is not None]
    return {
        "attempted": len(results), "executed": len(results) - outcomes["execution_error"],
        "passed": outcomes["pass"], "failed": outcomes["fail"], "execution_errors": outcomes["execution_error"],
        "metrics": metrics,
        "categories": categories,
        "provider_error_counts": dict(Counter(r["execution"]["error_kind"] for r in results
                                               if r["execution"]["error_kind"])),
        "generation_calls_initiated": sum(r["execution"].get("generation_call_initiated", False) for r in results),
        "latency_ms_total": round(sum(r["execution"]["latency_ms"] for r in results), 3),
        "usage": {"responses_with_usage": len(usages),
                  "input_tokens": sum(u["input_tokens"] for u in usages),
                  "output_tokens": sum(u["output_tokens"] for u in usages)} if usages else None,
        "cost_usd": None,
        "cost_note": "Unavailable: no verified pricing configuration; no monetary estimate is made.",
    }
