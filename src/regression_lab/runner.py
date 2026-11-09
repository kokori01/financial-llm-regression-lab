"""One small runner shared by replay and optional live adapters."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from importlib import metadata
from pathlib import Path
import platform
from time import perf_counter
from typing import Any, Protocol

from . import __version__
from .comparison import compare, summarize
from .dataset import case_input, resource_hash
from .evaluators import evaluate, execution_error
from .schemas import Case, RESPONSE_CONTRACT_VERSION, ReplayFixture, Snapshot

SYNTHETIC_NOTICE = "Synthetic demonstration, not real model benchmark results."


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Execution:
    raw_response: str | None
    started_at: str
    latency_ms: float
    requested_model: str | None = None
    returned_model: str | None = None
    usage: dict[str, int] | None = None
    error_kind: str | None = None
    error_message: str | None = None
    provider_status: str = "completed"
    response_id: str | None = None
    injected_defect: str | None = None
    refusal: bool = False
    provider_settings: dict[str, Any] | None = None
    incomplete_reason: str | None = None
    generation_call_initiated: bool = False
    cost_usd: None = None


class Provider(Protocol):
    mode: str
    label: str
    configuration: dict[str, Any]

    def execute(self, case_id: str, input_text: str) -> Execution: ...


class ReplayProvider:
    mode = "offline_replay"

    def __init__(self, fixture: ReplayFixture):
        self.fixture = fixture
        self.label = fixture.label
        self.configuration = {"id": fixture.configuration_id, "model": None,
                              "synthetic": True, "notice": SYNTHETIC_NOTICE}

    def execute(self, case_id: str, input_text: str) -> Execution:
        started = utc_now()
        tick = perf_counter()
        item = self.fixture.responses[case_id]
        return Execution(raw_response=item.raw_response, started_at=started,
                         latency_ms=round((perf_counter() - tick) * 1000, 3),
                         injected_defect=item.injected_defect)


def engine_hash() -> str:
    digest = sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def run_experiment(snapshot: Snapshot, cases: list[Case], baseline: Provider,
                   candidate: Provider) -> dict[str, Any]:
    if baseline.mode != candidate.mode or baseline.label != "baseline" or candidate.label != "candidate":
        raise ValueError("Need baseline and candidate providers in the same execution mode")
    if baseline.configuration == candidate.configuration:
        raise ValueError("Configurations must differ")
    started = utc_now()
    tick = perf_counter()
    runs: dict[str, Any] = {
        p.label: {"configuration": p.configuration, "results": []} for p in (baseline, candidate)
    }
    for case in cases:
        input_text = case_input(case, snapshot)
        input_hash = sha256(input_text.encode()).hexdigest()
        for provider in (baseline, candidate):
            execution = provider.execute(case.id, input_text)
            if execution.error_kind:
                evaluation = execution_error(execution.error_message or execution.error_kind)
            else:
                if execution.raw_response is None:
                    raise ValueError("Adapter returned neither a response nor an execution error")
                evaluation = evaluate(case, snapshot.facts, execution.raw_response,
                                      complete=execution.provider_status == "completed", refused=execution.refusal)
            runs[provider.label]["results"].append({
                "case_id": case.id, "title": case.title, "category": case.category,
                "input_sha256": input_hash,
                "expected": {"status": case.expected_status, "value": case.gold_value,
                             "period": case.expected_period.model_dump() if case.expected_period else None,
                             "unit": case.expected_unit, "tolerance": case.tolerance,
                             "rounding_digits": case.rounding_digits, "derivation": case.gold_derivation},
                "execution": asdict(execution), "evaluation": evaluation.model_dump(),
            })
    for run in runs.values():
        run["summary"] = summarize(run["results"])
    hashes = {path: resource_hash(path) for path in ["data/sec_facts_snapshot.json", "data/cases.json"]}
    if baseline.mode == "offline_replay":
        hashes.update({f"fixtures/{label}_responses.json": resource_hash(f"fixtures/{label}_responses.json")
                       for label in ("baseline", "candidate")})
    return {
        "report_version": 2, "application_version": __version__, "engine_sha256": engine_hash(),
        "evaluation_configuration": {
            "response_contract_version": RESPONSE_CONTRACT_VERSION,
            "benchmark_id": "apple-financial-qa-12-v2",
            "numeric_comparison": "inclusive absolute Decimal tolerance around rounded independent gold",
            "rounding": "ROUND_HALF_UP; percentages 2 decimals; billions 3; direct millions exact",
            "text_policy": "model prose forbidden; application display rendered only for passing cases",
            "ordering": "baseline then candidate for each case; one response per configuration/case",
        },
        "environment": {"python": platform.python_version(), "pydantic": metadata.version("pydantic")},
        "mode": baseline.mode, "notice": SYNTHETIC_NOTICE if baseline.mode == "offline_replay" else
        "Live provider execution; this small single-run evaluation is not a general model benchmark.",
        "started_at": started, "finished_at": utc_now(), "runtime_ms": round((perf_counter() - tick) * 1000, 3),
        "dataset": snapshot.model_dump(exclude={"facts"}), "resource_sha256": hashes,
        "case_count": len(cases), "response_attempts": len(cases) * 2,
        "runs": runs,
        "comparison": compare(runs["baseline"]["results"], runs["candidate"]["results"]),
        "limitations": [
            "Synthetic replay checks the harness, not any real model's quality, latency or cost.",
            "Seven facts from one frozen Apple filing and twelve overlapping cases provide no statistical generalization.",
            "Pass means all applicable deterministic checks passed. General text semantics are not evaluated; model prose is forbidden by contract v2.",
            "Display answers are application-rendered only for passing cases. This constrains the interface, not a solution to general semantic faithfulness.",
            "Period checks compare both the model's structured claim and cited fact metadata against the curated expected periods.",
            "Citation support covers predefined formulas and operands, not arbitrary financial claims or reasoning chains.",
            "The two adversarial cases are narrow probes, not a general prompt-injection security assessment.",
            "Numeric/unit/citation metrics are conditional on a schema-valid answer; consult not-evaluated counts and overall outcomes.",
            "Execution errors are not model failures and make the affected pair not comparable.",
            "No pricing configuration is bundled; cost is unavailable. Replay latency measures fixture lookup only.",
            "Contract v2 changes the model interface and C05's representation; its scores are not directly comparable to v1 model runs.",
        ],
    }
