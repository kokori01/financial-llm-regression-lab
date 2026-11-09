"""Load frozen local resources and independently reconcile gold arithmetic."""

from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from importlib.resources import files
from typing import Any

from .schemas import Case, Fact, Operand, ReplayFixture, Snapshot, strict_json


def read_resource(relative: str) -> str:
    return files("regression_lab").joinpath("resources", relative).read_text(encoding="utf-8")


def resource_hash(relative: str) -> str:
    return sha256(read_resource(relative).encode()).hexdigest()


def matches(fact: Fact, operand: Operand) -> bool:
    return all(getattr(fact, field) == getattr(operand, field) for field in Operand.model_fields)


def calculate(operation: str, values: list[int]) -> Decimal:
    """Small explicit formula allowlist; model output is never executed."""
    nums = [Decimal(v) for v in values]
    if operation == "lookup":
        return nums[0]
    if operation == "millions_to_billions":
        return nums[0] / Decimal(1000)
    if operation == "growth_percent":
        if nums[1] == 0:
            raise ValueError("Growth denominator is zero")
        return (nums[0] - nums[1]) / nums[1] * 100
    if operation == "ratio_percent":
        if nums[1] == 0:
            raise ValueError("Margin denominator is zero")
        return nums[0] / nums[1] * 100
    raise ValueError(f"Unknown numeric operation: {operation}")


def load_benchmark() -> tuple[Snapshot, list[Case]]:
    snapshot = Snapshot.model_validate(strict_json(read_resource("data/sec_facts_snapshot.json")))
    cases = [Case.model_validate(row) for row in strict_json(read_resource("data/cases.json"))]
    validate_benchmark(snapshot, cases)
    return snapshot, cases


def validate_benchmark(snapshot: Snapshot, cases: list[Case]) -> None:
    if sorted(c.id for c in cases) != [f"C{i:02}" for i in range(1, 13)]:
        raise ValueError("Benchmark requires exactly C01 through C12, once each")
    by_id = {f.source_id: f for f in snapshot.facts}
    if len(by_id) != len(snapshot.facts):
        raise ValueError("Duplicate source IDs")
    for case in cases:
        if set(case.evidence_ids) - by_id.keys():
            raise ValueError(f"{case.id}: unknown evidence IDs")
        if case.operation == "unavailable":
            if any(by_id[s].metric == case.target_metric
                   and by_id[s].fiscal_year == case.target_fiscal_year for s in case.evidence_ids):
                raise ValueError(f"{case.id}: expected missing fact is present")
            continue
        metrics = [case.target_metric]
        years = [case.target_fiscal_year]
        if case.operation == "growth_percent":
            if case.target_metric != "net_sales_growth":
                raise ValueError(f"{case.id}: unsupported growth target")
            metrics, years = ["net_sales", "net_sales"], [case.target_fiscal_year, case.target_fiscal_year - 1]
        elif case.operation == "ratio_percent":
            numerators = {"gross_margin_percentage": "gross_margin", "operating_margin_percentage": "operating_income"}
            if case.target_metric not in numerators:
                raise ValueError(f"{case.id}: unsupported margin target")
            metrics, years = [numerators[case.target_metric], "net_sales"], [case.target_fiscal_year] * 2
        if [(o.metric, o.fiscal_year) for o in case.operands] != list(zip(metrics, years, strict=True)):
            raise ValueError(f"{case.id}: formula operands disagree with the requested metric/year")
        values = []
        for operand in case.operands:
            supporting = [by_id[s] for s in case.evidence_ids if matches(by_id[s], operand)]
            if len(supporting) != 1:
                raise ValueError(f"{case.id}: expected exactly one fact for {operand.metric} FY{operand.fiscal_year}")
            values.append(supporting[0].value)
        period = case.expected_period
        assert period is not None
        if period.basis != "fiscal" or period.year != case.target_fiscal_year or not any(
            op.fiscal_year == period.year and op.period_start == period.start and op.period_end == period.end
            for op in case.operands
        ):
            raise ValueError(f"{case.id}: expected period disagrees with target-year evidence")
        result = calculate(case.operation, values).quantize(
            Decimal(1).scaleb(-case.rounding_digits), rounding=ROUND_HALF_UP
        )
        if result != Decimal(str(case.gold_value)):
            raise ValueError(f"{case.id}: independent gold disagrees with evidence/formula")
        unit = {"lookup": "USD_millions", "millions_to_billions": "USD_billions",
                "growth_percent": "percent", "ratio_percent": "percent"}[case.operation]
        if case.expected_unit != unit:
            raise ValueError(f"{case.id}: gold unit disagrees with formula")


def load_fixture(label: str, cases: list[Case]) -> ReplayFixture:
    if label not in {"baseline", "candidate"}:
        raise ValueError("Unknown replay label")
    fixture = ReplayFixture.model_validate(strict_json(read_resource(f"fixtures/{label}_responses.json")))
    if fixture.label != label or set(fixture.responses) != {c.id for c in cases}:
        raise ValueError("Fixture label/case coverage mismatch")
    return fixture


def case_input(case: Case, snapshot: Snapshot) -> str:
    """Same question/evidence bytes for both configurations; never send gold fields."""
    import json

    by_id = {f.source_id: f for f in snapshot.facts}
    packet: dict[str, Any] = {
        "case_id": case.id,
        "question": case.question,
        "evidence": [by_id[s].model_dump() for s in case.evidence_ids],
    }
    if case.synthetic_untrusted_text:
        packet["untrusted_attachment"] = {
            "synthetic": True, "text": case.synthetic_untrusted_text,
            "is_financial_source": False,
        }
    return json.dumps(packet, ensure_ascii=False, sort_keys=True)
