import json

import pytest
from pydantic import ValidationError

from regression_lab.schemas import parse_response

PERIOD = {"basis": "fiscal", "year": 2025, "start": "2024-09-29", "end": "2025-09-27"}
VALID = {"status": "answered", "period": PERIOD, "value": 416161,
         "unit": "USD_millions", "citations": ["AAPL_FY2025_SALES"]}


def test_accepts_actual_numbers_and_json_whitespace():
    assert parse_response("\n " + json.dumps(VALID) + " \n").value == 416161


@pytest.mark.parametrize("change", [
    {"value": "416161"}, {"value": True}, {"value": None}, {"value": float("nan")},
    {"value": float("inf")}, {"unit": "USD"}, {"unit": "not_applicable"},
    {"unexpected": 1}, {"answer": "   "}, {"answer": 42}, {"status": "unknown"},
    {"citations": "AAPL_FY2025_SALES"}, {"citations": [1]},
    {"citations": ["AAPL_FY2025_SALES", "AAPL_FY2025_SALES"]},
    {"status": "insufficient_evidence"},
])
def test_strict_types_fields_and_status_constraints(change):
    with pytest.raises((ValueError, ValidationError)):
        parse_response(json.dumps(VALID | change))


@pytest.mark.parametrize("raw", [
    '```json\n' + json.dumps(VALID) + '\n```',
    'Here it is: ' + json.dumps(VALID), json.dumps(VALID) + ' done',
    json.dumps(VALID) + json.dumps(VALID), '[]', 'null', '42',
    json.dumps(VALID).replace('416161', '1e999'),
    '{"status":"answered",' + json.dumps(VALID)[1:],
])
def test_noncontract_json_rejected(raw):
    with pytest.raises((ValueError, ValidationError)):
        parse_response(raw)


@pytest.mark.parametrize("field", list(VALID))
def test_every_field_is_required(field):
    response = dict(VALID)
    del response[field]
    with pytest.raises(ValidationError):
        parse_response(json.dumps(response))


def test_abstention_contract():
    abstain = {"status": "insufficient_evidence", "period": None,
               "value": None, "unit": "not_applicable", "citations": []}
    assert parse_response(json.dumps(abstain)).status == "insufficient_evidence"
    for change in [{"value": 0}, {"unit": "USD_millions"}, {"citations": ["AAPL_FY2025_SALES"]}, {"period": PERIOD}]:
        with pytest.raises(ValidationError):
            parse_response(json.dumps(abstain | change))


@pytest.mark.parametrize("period", [None, {}, PERIOD | {"year": "2025"}, PERIOD | {"year": True},
    PERIOD | {"start": "2025-02-30"}, PERIOD | {"start": "20250929"},
    PERIOD | {"start": "2026-01-01"}, PERIOD | {"basis": "annual"},
    PERIOD | {"explanation": "Calendar 2025"}])
def test_period_contract(period):
    with pytest.raises(ValidationError):
        parse_response(json.dumps(VALID | {"period": period}))
