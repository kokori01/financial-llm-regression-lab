"""Real SDK request/response handling with local mocked HTTP; never live inference."""

import json

import pytest

openai = pytest.importorskip("openai")
import httpx

from regression_lab.cli import main
from regression_lab.dataset import case_input
from regression_lab.evaluators import evaluate
from regression_lab.providers import LiveConfig, OpenAIProvider, validate_models


def client(handler, retries=0):
    return openai.OpenAI(api_key="test-only-not-a-credential", max_retries=retries,
                         http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def envelope(text, status="completed"):
    return {"id": "resp_local_test", "object": "response", "created_at": 0, "status": status,
            "model": "unit-test-model-snapshot", "output": [{"id": "msg_test", "type": "message",
            "role": "assistant", "status": "completed", "content": [{"type": "output_text",
            "text": text, "annotations": []}]}], "usage": {"input_tokens": 100, "output_tokens": 50,
            "total_tokens": 150, "input_tokens_details": {"cached_tokens": 10},
            "output_tokens_details": {"reasoning_tokens": 20}}}


def test_sdk_interface_and_identical_case_inputs(benchmark, baseline):
    requests = []
    def handler(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"id": "unit-test-model", "object": "model", "created": 0, "owned_by": "test"})
        return httpx.Response(200, json=envelope(baseline.responses["C01"].raw_response))
    with client(handler) as api:
        availability = validate_models(api, ["unit-test-model", "unit-test-model"])
        assert list(availability) == ["unit-test-model"]
        packet = case_input(benchmark[1][0], benchmark[0])
        outputs = []
        for label, prompt in [("baseline", "strict-v2"), ("candidate", "explicit-v3")]:
            adapter = OpenAIProvider(api, label, LiveConfig("unit-test-model", prompt), authorized=True)
            outputs.append(adapter.execute("C01", packet))
    assert len(requests) == 3 and requests[0].url.path == "/v1/models/unit-test-model"
    bodies = [json.loads(r.content) for r in requests[1:]]
    assert bodies[0]["input"] == bodies[1]["input"] == packet
    assert bodies[0]["instructions"] != bodies[1]["instructions"]
    assert all(b["store"] is False and b["temperature"] == 0 and b["service_tier"] == "default" for b in bodies)
    assert all(r.url.path == "/v1/responses" for r in requests[1:])
    for result in outputs:
        assert result.raw_response == baseline.responses["C01"].raw_response
        assert result.returned_model == "unit-test-model-snapshot"
        assert result.usage == {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
                               "cached_input_tokens": 10, "reasoning_output_tokens": 20}
        assert result.latency_ms >= 0 and result.cost_usd is None


@pytest.mark.parametrize("status,kind", [(400, "invalid_configuration"), (401, "invalid_configuration"),
    (403, "invalid_configuration"), (404, "invalid_configuration"), (408, "timeout"),
    (429, "rate_limit"), (500, "provider_error")])
def test_api_errors_are_separate_and_redacted(status, kind):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(status, json={"error": {"message": "private-detail-do-not-leak", "type": "test_error"}})
    with client(handler) as api:
        adapter = OpenAIProvider(api, "baseline", LiveConfig("unit-test-model", "strict-v2", max_retries=0), authorized=True)
        first, second = adapter.execute("C01", "{}"), adapter.execute("C02", "{}")
    assert first.error_kind == second.error_kind == kind
    assert "private-detail" not in str(first)
    assert len(requests) == (1 if kind == "invalid_configuration" else 2)


@pytest.mark.parametrize("exception,kind", [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "network_error")])
def test_network_and_timeout_are_not_output_failures(exception, kind):
    def handler(request):
        raise exception("private-detail", request=request)
    with client(handler) as api:
        result = OpenAIProvider(api, "baseline", LiveConfig("unit-test-model", "strict-v2", max_retries=0),
                                authorized=True).execute("C01", "{}")
    assert result.error_kind == kind and result.raw_response is None
    assert "private-detail" not in result.error_message


def test_bounded_retry_then_success(baseline):
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after-ms": "1"}, json={"error": {"message": "rate limit"}})
        return httpx.Response(200, json=envelope(baseline.responses["C01"].raw_response))
    with client(handler) as api:
        result = OpenAIProvider(api, "baseline", LiveConfig("unit-test-model", "strict-v2", max_retries=1),
                                authorized=True).execute("C01", "{}")
    assert len(calls) == 2 and result.error_kind is None


def test_preflight_failure_prevents_generation():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(404, json={"error": {"message": "not available"}})
    with client(handler) as api:
        with pytest.raises(ValueError, match="availability preflight failed"):
            validate_models(api, ["unit-test-model"])
    assert len(calls) == 1 and calls[0].method == "GET"


def test_incomplete_valid_json_still_fails_and_temperature_can_be_omitted(benchmark, baseline):
    bodies = []
    def handler(request):
        bodies.append(json.loads(request.content))
        data = envelope(baseline.responses["C11"].raw_response, "incomplete")
        data['incomplete_details'] = {'reason': 'max_output_tokens'}
        return httpx.Response(200, json=data)
    with client(handler) as api:
        result = OpenAIProvider(api, "baseline", LiveConfig("unit-test-model", "strict-v2", temperature=None),
                                authorized=True).execute("C11", "{}")
    assert "temperature" not in bodies[0]
    assert result.incomplete_reason == 'max_output_tokens'
    evaluated = evaluate(benchmark[1][10], benchmark[0].facts, result.raw_response,
                         complete=result.provider_status == "completed")
    assert evaluated.outcome == "fail" and evaluated.checks["schema"].state == "pass"
    assert evaluated.checks["instruction_resistance"].state == "fail"


def test_refusal_is_schema_failure_not_network_error(benchmark):
    def handler(request):
        data = envelope("")
        data["output"][0]["content"] = [{"type": "refusal", "refusal": "Cannot answer."}]
        return httpx.Response(200, json=data)
    with client(handler) as api:
        result = OpenAIProvider(api, "baseline", LiveConfig("unit-test-model", "strict-v2"),
                                authorized=True).execute("C01", "{}")
    assert result.error_kind is None
    assert evaluate(benchmark[1][0], benchmark[0].facts, result.raw_response).checks["schema"].state == "fail"


def test_paid_execution_requires_authorization(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    args = ["live", "--baseline-model", "unit-test-model", "--candidate-model", "unit-test-model"]
    assert main(args) == 2
    assert main(args + ["--allow-paid-api"]) == 2  # Missing credential, no network.
    with pytest.raises(ValueError, match="authorization"):
        OpenAIProvider(None, "baseline", LiveConfig("unit-test-model", "strict-v2"))


@pytest.mark.parametrize("change", [{"model": " "}, {"temperature": float("nan")},
    {"temperature": 3}, {"timeout_seconds": 0}, {"max_output_tokens": 0}, {"max_retries": 3}])
def test_invalid_live_configuration(change):
    with pytest.raises(ValueError):
        LiveConfig(**({"model": "unit-test-model", "prompt_id": "strict-v2"} | change))


def test_exhausted_quota_stops_remaining_calls():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"message": "private account detail",
                                                   "code": "insufficient_quota", "type": "insufficient_quota"}})
    with client(handler) as api:
        adapter = OpenAIProvider(api, "baseline", LiveConfig("unit-test-model", "strict-v2", max_retries=0), authorized=True)
        first, second = adapter.execute("C01", "{}"), adapter.execute("C02", "{}")
    assert first.error_kind == second.error_kind == "quota_exhausted"
    assert len(calls) == 1 and first.generation_call_initiated and not second.generation_call_initiated
    assert second.provider_status == "skipped"


@pytest.mark.parametrize("status", ["failed", "queued", "in_progress"])
def test_unexpected_provider_states_are_execution_errors(baseline, status):
    def handler(request):
        return httpx.Response(200, json=envelope(baseline.responses["C01"].raw_response, status))
    with client(handler) as api:
        result = OpenAIProvider(api, "baseline", LiveConfig("unit-test-model", "strict-v2"), authorized=True).execute("C01", "{}")
    assert result.error_kind == "provider_error"


def test_refusal_cannot_hide_beside_valid_json(benchmark, baseline):
    def handler(request):
        body = envelope(baseline.responses["C01"].raw_response)
        body["output"][0]["content"].append({"type": "refusal", "refusal": "Cannot answer."})
        return httpx.Response(200, json=body)
    with client(handler) as api:
        result = OpenAIProvider(api, "baseline", LiveConfig("unit-test-model", "strict-v2"), authorized=True).execute("C01", "{}")
    assert result.refusal is True
    evaluated = evaluate(benchmark[1][0], benchmark[0].facts, result.raw_response, refused=result.refusal)
    assert evaluated.checks["schema"].state == "pass"
    assert evaluated.outcome == "fail" and evaluated.rendered_answer is None


def test_missing_usage_is_unavailable_not_zero(baseline):
    def handler(request):
        body = envelope(baseline.responses["C01"].raw_response)
        body["usage"] = None
        body.update(temperature=0.7, top_p=1.0, reasoning={"effort": "low"}, service_tier="default")
        return httpx.Response(200, json=body)
    with client(handler) as api:
        result = OpenAIProvider(api, "baseline", LiveConfig("unit-test-model", "strict-v2"), authorized=True).execute("C01", "{}")
    assert result.usage is None and result.cost_usd is None
    assert result.provider_settings == {"temperature": 0.7, "top_p": 1.0, "reasoning": {"effort": "low"}, "service_tier": "default"}


def test_complete_live_cli_with_mock_transport(benchmark, baseline, candidate, tmp_path, monkeypatch):
    """Exercise preflight -> two configurations -> all cases -> live-labeled reports."""
    import regression_lab.providers as providers
    requests = []
    def handler(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"id": "unit-test-model", "object": "model", "created": 0, "owned_by": "test"})
        body = json.loads(request.content)
        case_id = json.loads(body["input"])["case_id"]
        fixture = candidate if "Before answering, check" in body["instructions"] else baseline
        return httpx.Response(200, json=envelope(fixture.responses[case_id].raw_response))
    monkeypatch.setattr(providers, "create_client", lambda config: client(handler))
    args = ["live", "--baseline-model", "unit-test-model", "--candidate-model", "unit-test-model",
            "--allow-paid-api", "--output-dir", str(tmp_path)]
    assert main(args) == 0
    report = json.loads((tmp_path / "comparison.json").read_text())
    assert len(requests) == 25  # One shared model retrieval, 24 local mocked generations.
    assert report["mode"] == "live" and report["comparison_type"] == "prompt_configuration"
    assert report["runs"]["candidate"]["summary"]["passed"] == 3
    assert all(r["execution"]["injected_defect"] is None for run in report["runs"].values() for r in run["results"])
    assert report["runs"]["baseline"]["summary"]["usage"]["input_tokens"] == 1200
    assert report["runs"]["candidate"]["summary"]["generation_calls_initiated"] == 12


def test_explicit_reasoning_setting_is_sent_and_recorded(baseline):
    bodies = []
    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=envelope(baseline.responses["C01"].raw_response))
    config = LiveConfig("unit-test-model", "strict-v2", temperature=None, reasoning_effort="low")
    with client(handler) as api:
        adapter = OpenAIProvider(api, "baseline", config, authorized=True)
        adapter.execute("C01", "{}")
    assert bodies[0]["reasoning"] == {"effort": "low"}
    assert "temperature" not in bodies[0]
    assert adapter.configuration["reasoning_effort"] == "low"


@pytest.mark.parametrize("broken", ["missing_output", "invalid_usage", "missing_usage_count"])
def test_bad_provider_envelope_is_not_a_model_failure(baseline, broken):
    def handler(request):
        body = envelope(baseline.responses["C01"].raw_response)
        if broken == "missing_output":
            body.pop("output")
        elif broken == "missing_usage_count":
            body["usage"].pop("input_tokens")
        else:
            body["usage"]["input_tokens"] = -1
        return httpx.Response(200, json=body)
    with client(handler) as api:
        result = OpenAIProvider(api, "baseline", LiveConfig("unit-test-model", "strict-v2"), authorized=True).execute("C01", "{}")
    assert result.error_kind == "provider_protocol_error" and result.raw_response is None


def test_read_only_preflight_never_generates(tmp_path, monkeypatch, capsys):
    import regression_lab.providers as providers
    requests = []
    def handler(request):
        requests.append(request)
        assert request.method == 'GET'
        return httpx.Response(200, json={'id': request.url.path.split('/')[-1], 'object': 'model',
                                        'created': 0, 'owned_by': 'test'})
    monkeypatch.setattr(providers, 'create_client', lambda config: client(handler))
    assert main(['live', '--baseline-model', 'gpt-5.6-terra', '--candidate-model', 'gpt-6.1-terra',
                 '--candidate-prompt', 'strict-v2', '--max-retries', '0', '--preflight-only']) == 0
    assert len(requests) == 2
    assert 'no generation calls' in capsys.readouterr().out


def test_budgeted_cli_mock_end_to_end_preserves_settings_and_reports(benchmark, baseline, tmp_path, monkeypatch):
    from pathlib import Path
    import regression_lab.providers as providers
    requests = []
    def handler(request):
        requests.append(request)
        if request.method == 'GET':
            return httpx.Response(200, json={'id': request.url.path.split('/')[-1], 'object': 'model',
                                            'created': 0, 'owned_by': 'test'})
        body = json.loads(request.content)
        case_id = json.loads(body['input'])['case_id']
        data = envelope(baseline.responses[case_id].raw_response)
        data.update(model=body['model'], service_tier='default', reasoning={'effort': 'low'})
        return httpx.Response(200, json=data)
    monkeypatch.setattr(providers, 'create_client', lambda config: client(handler))
    pricing = Path(__file__).parents[1] / 'docs/live_pricing_2026-11-09.json'
    args = ['live', '--baseline-model', 'gpt-5.6-terra', '--candidate-model', 'gpt-6.1-terra',
            '--candidate-prompt', 'strict-v2', '--max-retries', '0', '--omit-temperature',
            '--reasoning-effort', 'low', '--max-output-tokens', '4096', '--budget-usd', '2',
            '--pricing-file', str(pricing), '--output-dir', str(tmp_path), '--allow-paid-api']
    assert main(args) == 0
    assert len(requests) == 26  # 2 GET + 24 mocked POST, no retries or extra generations.
    bodies = [json.loads(r.content) for r in requests if r.method == 'POST']
    assert len({b['instructions'] for b in bodies}) == 1
    for b in bodies:
        assert 'text' not in b and 'temperature' not in b and 'tools' not in b
        assert b['reasoning'] == {'effort': 'low'} and b['max_output_tokens'] == 4096
        assert b['service_tier'] == 'default' and b['store'] is False
    for i in range(0,24,2):
        assert bodies[i]['input'] == bodies[i+1]['input']
    report = json.loads((tmp_path/'comparison.json').read_text())
    assert report['cost_monitor']['initiated_calls'] == 24
    assert report['cost_monitor']['stop_reason'] is None
    assert report['cost_monitor']['all_initiated_calls_have_valid_usage']
    assert 'Estimated API cost' in (tmp_path/'comparison.md').read_text()
    assert len((tmp_path/'comparison.calls.jsonl').read_text().splitlines()) == 49
    assert main(args) == 2  # Refuse to overwrite or repeat the funded experiment.
    assert len(requests) == 26
