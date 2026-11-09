"""Optional OpenAI Responses adapter. Importing this module does not require the SDK."""

from dataclasses import dataclass
from hashlib import sha256
from importlib import metadata
import math
import os
from time import perf_counter
from typing import Any

from .prompts import PROMPT_ADDITIONS, system_prompt
from .runner import Execution, utc_now


@dataclass(frozen=True)
class LiveConfig:
    model: str
    prompt_id: str
    temperature: float | None = 0.0
    max_output_tokens: int = 2048
    timeout_seconds: float = 45.0
    max_retries: int = 1
    reasoning_effort: str | None = None

    def __post_init__(self) -> None:
        if not self.model.strip() or self.model != self.model.strip() or len(self.model) > 200:
            raise ValueError("An explicit, nonblank model ID is required")
        if self.prompt_id not in PROMPT_ADDITIONS:
            raise ValueError("Unknown prompt configuration")
        if self.temperature is not None and (not math.isfinite(self.temperature) or not 0 <= self.temperature <= 2):
            raise ValueError("temperature must be finite and between 0 and 2")
        if not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 120:
            raise ValueError("timeout must be positive and at most 120 seconds")
        if not 1 <= self.max_output_tokens <= 8192 or not 0 <= self.max_retries <= 2:
            raise ValueError("max_output_tokens must be 1..8192 and max_retries must be 0..2")
        if self.reasoning_effort not in {None, "none", "low", "medium", "high"}:
            raise ValueError("Unsupported reasoning effort setting")

    def describe(self) -> dict[str, Any]:
        prompt = system_prompt(self.prompt_id)
        return {"id": f"{self.model}:{self.prompt_id}", "model": self.model, "prompt_id": self.prompt_id,
                "system_prompt": prompt, "system_prompt_sha256": sha256(prompt.encode()).hexdigest(),
                "temperature": self.temperature, "max_output_tokens": self.max_output_tokens,
                "timeout_seconds": self.timeout_seconds, "max_retries": self.max_retries,
                "interface": "OpenAI Responses API", "store": False,
                "service_tier": "default",
                "reasoning_effort": self.reasoning_effort,
                "output_format": "plain text; strict JSON is prompted and locally validated"}


def create_client(config: LiveConfig) -> Any:
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key.strip():
        raise ValueError("OPENAI_API_KEY is not set; use replay or live --dry-run")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ValueError("Optional SDK missing; install the project's [live] extra") from exc
    return OpenAI(api_key=key, base_url="https://api.openai.com/v1",
                  timeout=config.timeout_seconds, max_retries=config.max_retries)


def classify_api_error(exc: Exception) -> tuple[str, str]:
    """Never report raw provider exception bodies, headers or credentials."""
    from openai import APIConnectionError, APIStatusError, APITimeoutError

    if isinstance(exc, APITimeoutError):
        return "timeout", "Provider request timed out after the configured retry allowance."
    if isinstance(exc, APIConnectionError):
        return "network_error", "Could not connect to the provider after the configured retry allowance."
    if isinstance(exc, APIStatusError):
        status = exc.status_code
        if status in {400, 401, 403, 404, 422}:
            return "invalid_configuration", f"Provider rejected configuration/access (HTTP {status}); " \
                "check model access, credentials and supported parameters."
        if status == 429:
            if getattr(exc, "code", None) == "insufficient_quota":
                return "quota_exhausted", "Provider reports insufficient quota; remaining calls for this configuration will be skipped."
            return "rate_limit", "Provider rate/quota limit (HTTP 429); usage or credits may be unavailable."
        if status == 408:
            return "timeout", "Provider request timeout (HTTP 408) after the configured retry allowance."
        return "provider_error", f"Provider HTTP error {status}; not a model-quality result."
    return "provider_error", "Provider SDK error; raw exception details omitted."


def validate_models(client: Any, model_ids: list[str]) -> dict[str, Any]:
    """Read-only account-specific preflight, before any generation request."""
    from openai import APIError

    checked = {}
    for model_id in dict.fromkeys(model_ids):
        try:
            model = client.models.retrieve(model_id)
        except APIError as exc:
            kind, message = classify_api_error(exc)
            raise ValueError(f"Model availability preflight failed ({kind}): {message}") from None
        checked[model_id] = {"returned_id": model.id, "checked_at": utc_now(),
                             "scope": "Account model retrieval succeeded; generation/parameter support not proven."}
    return checked


class OpenAIProvider:
    mode = "live"

    def __init__(self, client: Any, label: str, config: LiveConfig, *, authorized: bool = False):
        if not authorized:
            raise ValueError("Live generation requires explicit paid-API authorization")
        if label not in {"baseline", "candidate"}:
            raise ValueError("Unknown provider label")
        self.client = client.with_options(timeout=config.timeout_seconds, max_retries=config.max_retries)
        self.label, self.config = label, config
        self.configuration = config.describe() | {"sdk_version": metadata.version("openai")}
        self.blocked_error: tuple[str, str] | None = None

    def execute(self, case_id: str, input_text: str) -> Execution:
        from openai import APIError

        started, tick = utc_now(), perf_counter()
        if self.blocked_error:
            return Execution(None, started, 0.0, requested_model=self.config.model,
                             error_kind=self.blocked_error[0],
                             provider_status="skipped",
                             error_message="Skipped: this configuration was already rejected by the provider.")
        kwargs: dict[str, Any] = {
            "model": self.config.model, "instructions": system_prompt(self.config.prompt_id),
            "input": input_text, "store": False, "max_output_tokens": self.config.max_output_tokens,
            "service_tier": "default",
        }
        if self.config.temperature is not None:
            kwargs["temperature"] = self.config.temperature
        if self.config.reasoning_effort is not None:
            kwargs["reasoning"] = {"effort": self.config.reasoning_effort}
        try:
            response = self.client.responses.create(**kwargs)
        except APIError as exc:
            kind, message = classify_api_error(exc)
            if kind in {"invalid_configuration", "quota_exhausted"}:
                self.blocked_error = (kind, message)
            return Execution(None, started, round((perf_counter() - tick) * 1000, 3),
                             requested_model=self.config.model, error_kind=kind, error_message=message,
                             provider_status="request_error", generation_call_initiated=True)
        if (not isinstance(getattr(response, "output", None), list)
                or not isinstance(getattr(response, "id", None), str)
                or not isinstance(getattr(response, "model", None), str)):
            return Execution(None, started, round((perf_counter() - tick) * 1000, 3),
                             requested_model=self.config.model, error_kind="provider_protocol_error",
                             error_message="Provider response envelope is missing required metadata/output.",
                             provider_status="invalid_envelope", generation_call_initiated=True)
        usage = None
        if response.usage is not None:
            usage = {name: getattr(response.usage, name, None)
                     for name in ("input_tokens", "output_tokens", "total_tokens")}
            if any(type(value) is not int or value < 0 for value in usage.values()):
                return Execution(None, started, round((perf_counter() - tick) * 1000, 3),
                                 requested_model=self.config.model, error_kind="provider_protocol_error",
                                 error_message="Provider returned invalid token usage metadata.",
                                 provider_status="invalid_envelope", generation_call_initiated=True)
            for key, detail, attribute in [
                ("cached_input_tokens", getattr(response.usage, "input_tokens_details", None), "cached_tokens"),
                ("reasoning_output_tokens", getattr(response.usage, "output_tokens_details", None), "reasoning_tokens"),
            ]:
                value = getattr(detail, attribute, None)
                if value is not None:
                    usage[key] = value
        failed = response.status not in {"completed", "incomplete"}
        refusal = any(getattr(content, "type", None) == "refusal" for item in response.output
                      for content in (getattr(item, "content", None) or []))
        settings = {"temperature": response.temperature, "top_p": response.top_p,
                    "service_tier": getattr(response, "service_tier", None),
                    "reasoning": response.reasoning.model_dump(exclude_none=True) if response.reasoning else None}
        return Execution(
            raw_response=response.output_text, started_at=started,
            latency_ms=round((perf_counter() - tick) * 1000, 3), requested_model=self.config.model,
            returned_model=response.model, usage=usage, response_id=response.id,
            provider_status=response.status or "unknown",
            refusal=refusal, provider_settings=settings, generation_call_initiated=True,
            incomplete_reason=getattr(getattr(response, "incomplete_details", None), "reason", None),
            error_kind="provider_error" if failed else None,
            error_message="Provider did not return a completed/incomplete generation; not scored as a model regression." if failed else None,
        )
