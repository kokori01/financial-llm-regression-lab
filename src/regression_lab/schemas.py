"""Strict output and benchmark contracts. No repairing model output."""

import json
from datetime import date
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Status = Literal["answered", "insufficient_evidence"]
Unit = Literal["USD_millions", "USD_billions", "percent", "not_applicable"]
SourceID = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]*$")]
RESPONSE_CONTRACT_VERSION = 2


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"Duplicate JSON field: {key}")
        obj[key] = value
    return obj


def _reject_constant(value: str) -> None:
    raise ValueError(f"Nonstandard JSON numeric constant: {value}")


def strict_json(raw: str) -> Any:
    """Reject fences, trailing prose, duplicate keys, NaN and Infinity."""
    return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)


class Period(StrictModel):
    basis: Literal["fiscal", "calendar"]
    year: int = Field(ge=1900, le=2100)
    start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

    @field_validator("start", "end")
    @classmethod
    def valid_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def ordered_dates(self) -> Self:
        if self.start > self.end:
            raise ValueError("period start must not follow period end")
        return self


class Response(StrictModel):
    """v2 accepts structured claims only; display prose is application-owned."""

    status: Status
    value: float | None
    unit: Unit
    period: Period | None
    citations: list[SourceID] = Field(max_length=7)

    @model_validator(mode="after")
    def status_contract(self) -> Self:
        if len(self.citations) != len(set(self.citations)):
            raise ValueError("citations must be unique")
        if self.status == "insufficient_evidence":
            if self.value is not None or self.unit != "not_applicable" or self.citations or self.period is not None:
                raise ValueError("abstention requires null value and period, not_applicable unit and no citations")
        elif self.value is None or self.unit == "not_applicable" or self.period is None:
            raise ValueError("answered requires a finite numeric value, numeric unit and period")
        return self


def parse_response(raw: str) -> Response:
    return Response.model_validate(strict_json(raw))


class SourceReference(StrictModel):
    url: str
    sec_url: str
    accession: str
    form: Literal["10-K"]
    filed_on: str
    section: str
    page: int
    row: str
    column: str


class Operand(StrictModel):
    """Required meaning of a supporting fact, independent of citation ID."""

    company: Literal["Apple Inc."]
    metric: str
    fiscal_year: int
    period_start: str
    period_end: str
    unit: Literal["USD_millions"]


class Fact(Operand):
    source_id: SourceID
    value: int
    source: SourceReference


class Snapshot(StrictModel):
    dataset_id: str
    description: str
    verified_on: str
    provenance: dict[str, str]
    facts: list[Fact]


class Case(StrictModel):
    id: str = Field(pattern=r"^C(0[1-9]|1[0-2])$")
    title: str
    category: Literal["financial_calculation", "data_interpretation", "source_validation",
                      "missing_information", "instruction_resistance"]
    question: str
    target_metric: str
    target_fiscal_year: int
    evidence_ids: list[SourceID]
    operation: Literal["lookup", "growth_percent", "ratio_percent", "millions_to_billions", "unavailable"]
    operands: list[Operand]
    expected_status: Status
    gold_value: float | None
    expected_unit: Unit
    tolerance: float = Field(ge=0)
    rounding_digits: int = Field(ge=0, le=6)
    gold_derivation: str
    expected_period: Period | None
    synthetic_untrusted_text: str | None

    @model_validator(mode="after")
    def valid_gold(self) -> Self:
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("duplicate evidence IDs")
        counts = {"lookup": 1, "growth_percent": 2, "ratio_percent": 2,
                  "millions_to_billions": 1, "unavailable": 0}
        if len(self.operands) != counts[self.operation]:
            raise ValueError("wrong number of formula operands")
        if self.operation == "unavailable":
            if (self.expected_status != "insufficient_evidence" or self.gold_value is not None
                    or self.expected_unit != "not_applicable" or self.expected_period is not None):
                raise ValueError("unavailable case requires an abstention gold")
        elif self.expected_status != "answered" or self.gold_value is None or self.expected_period is None:
            raise ValueError("answerable case requires a numeric gold and expected period")
        return self


class FixtureResponse(StrictModel):
    raw_response: str
    injected_defect: str | None


class ReplayFixture(StrictModel):
    synthetic: Literal[True]
    notice: str
    label: Literal["baseline", "candidate"]
    configuration_id: str
    responses: dict[str, FixtureResponse]


CheckState = Literal["pass", "fail", "not_evaluated"]


class Check(StrictModel):
    state: CheckState
    reason: str


class Evaluation(StrictModel):
    outcome: Literal["pass", "fail", "execution_error"]
    checks: dict[str, Check]
    failures: list[str]
    parsed_response: Response | None
    rendered_answer: str | None = None
