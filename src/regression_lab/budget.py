"""Conservative sequential spending monitor, not a provider-enforced dollar cap."""

from dataclasses import asdict
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any

from .dataset import case_input
from .prompts import system_prompt
from .runner import Execution, utc_now

MILLION = Decimal(1_000_000)


def positive(value: Any) -> Decimal:
    try:
        number = Decimal(str(value))
    except Exception:
        raise ValueError("Budget and price values must be positive finite numbers") from None
    if not number.is_finite() or number <= 0:
        raise ValueError("Budget and price values must be positive finite numbers")
    return number


def load_pricing(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("currency") != "USD" or data.get("service_tier") != "default":
        raise ValueError("Budget monitor requires USD default-tier pricing")
    if not data.get("verified_on") or not data.get("sources"):
        raise ValueError("Pricing requires verification date and sources")
    if positive(data["safety_multiplier"]) < 1:
        raise ValueError("Safety multiplier cannot reduce the estimate")
    for rates in data["models"].values():
        for field in ("input_per_million", "output_per_million", "input_ceiling_per_million"):
            positive(rates[field])
        if positive(rates["input_ceiling_per_million"]) < positive(rates["input_per_million"]):
            raise ValueError("Input ceiling must cover ordinary input pricing")
    return data


def estimate(pricing: dict, model: str, inputs: int, outputs: int, *, conservative: bool) -> Decimal:
    rates = pricing["models"][model]
    rate = rates["input_ceiling_per_million" if conservative else "input_per_million"]
    result = (Decimal(inputs) * positive(rate) + Decimal(outputs) * positive(rates["output_per_million"])) / MILLION
    return result * positive(pricing["safety_multiplier"]) if conservative else result


def budget_plan(snapshot, cases, configs, pricing: dict, limit: str) -> dict:
    maximum = positive(limit)
    entries = []
    for label, config in zip(("baseline", "candidate"), configs, strict=True):
        if config.max_retries != 0:
            raise ValueError("Budget monitoring requires zero SDK retries")
        if config.model not in pricing["models"]:
            raise ValueError("Missing verified price for a requested model")
        for case in cases:
            text = case_input(case, snapshot)
            size = len(system_prompt(config.prompt_id).encode("utf-8")) + len(text.encode("utf-8"))
            allowance = size + 1024
            entries.append({"label": label, "case_id": case.id, "model": config.model,
                            "configuration_sha256": sha256(json.dumps(config.describe(), sort_keys=True).encode()).hexdigest(),
                            "input_sha256": sha256(text.encode()).hexdigest(),
                            "request_text_utf8_bytes": size, "input_token_allowance": allowance,
                            "max_output_tokens": config.max_output_tokens,
                            "reservation_usd": str(estimate(pricing, config.model, allowance,
                                                            config.max_output_tokens, conservative=True))})
    total = sum((Decimal(e["reservation_usd"]) for e in entries), Decimal(0))
    return {"budget_usd": str(maximum), "planned_maximum_estimate_usd": str(total),
            "within_budget": total <= maximum, "generation_requests": len(entries),
            "pricing": pricing, "calls": entries,
            "hard_cap": False,
            "assumptions": ["Input allowance is one token per UTF-8 byte of instructions and input, plus 1024 framing tokens; not an exact provider token count.",
                            "Each reservation covers the full output limit, including reasoning, at conservative input rates and a safety multiplier.",
                            "No retries, tools, regional endpoint or non-default service tier. Estimates are pre-tax, not an invoice or account-wide cap.",
                            "Stop both configurations after any request error, missing/invalid usage or incompatible reported settings. Never retry automatically."]}


class BudgetLedger:
    def __init__(self, plan: dict, journal=None):
        self.plan = plan
        self.limit = positive(plan["budget_usd"])
        self.accounted = Decimal(0)
        self.calls: list[dict] = []
        self.stop_reason: str | None = None
        self.journal = journal
        self.seen: set[tuple[str, str]] = set()

    def record(self, event: dict) -> None:
        if self.journal is not None:
            self.journal.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
            self.journal.flush()
            os.fsync(self.journal.fileno())

    def summary(self) -> dict:
        return {"budget_usd": str(self.limit), "accounted_conservative_usd": str(self.accounted),
                "standard_rate_estimate_usd": str(sum((Decimal(c["standard_rate_estimate_usd"])
                    for c in self.calls if c.get("standard_rate_estimate_usd") is not None), Decimal(0))),
                "all_initiated_calls_have_valid_usage": all(c.get("usage_valid") for c in self.calls),
                "initiated_calls": len(self.calls), "stop_reason": self.stop_reason,
                "hard_cap": False, "pricing": self.plan["pricing"], "calls": self.calls,
                "note": "Estimates from reported usage, not an invoice. Standard estimate ignores cache discounts/write premiums; conservative accounting uses the input ceiling and safety margin. Unknown calls retain their entire reservation."}


class BudgetedProvider:
    """Wrap the existing adapter without changing output evaluation or prompts."""

    def __init__(self, provider, ledger: BudgetLedger):
        self.provider, self.ledger = provider, ledger
        self.mode, self.label = provider.mode, provider.label
        self.configuration = provider.configuration | {"spending_monitor": "shared sequential ledger; zero retries"}

    def execute(self, case_id: str, input_text: str) -> Execution:
        ledger = self.ledger
        key = (self.label, case_id)
        entry = next((e for e in ledger.plan["calls"] if (e["label"], e["case_id"]) == key), None)
        if (entry is None or key in ledger.seen or entry["input_sha256"] != sha256(input_text.encode()).hexdigest()
                or entry["model"] != self.provider.config.model
                or entry["configuration_sha256"] != sha256(json.dumps(self.provider.config.describe(), sort_keys=True).encode()).hexdigest()
                or entry["max_output_tokens"] != self.provider.config.max_output_tokens):
            ledger.stop_reason = "Request is outside the prepared experiment plan."
        reservation = Decimal(entry["reservation_usd"]) if entry else Decimal(0)
        if ledger.accounted + reservation > ledger.limit:
            ledger.stop_reason = "Next full-call reservation would exceed the spending limit."
        if ledger.stop_reason:
            return Execution(None, utc_now(), 0.0, requested_model=self.provider.config.model,
                             error_kind="budget_guard_stopped", error_message=ledger.stop_reason,
                             provider_status="skipped")
        ledger.seen.add(key)
        ledger.accounted += reservation
        ledger.record({"event": "reserved", "at": utc_now(), **entry,
                       "accounted_conservative_usd": str(ledger.accounted)})
        result = self.provider.execute(case_id, input_text)
        usage = result.usage
        valid = bool(usage) and all(type(usage.get(k)) is int and usage[k] >= 0
                                   for k in ("input_tokens", "output_tokens", "total_tokens"))
        valid = valid and usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"]
        if valid:
            for detail, total in (("cached_input_tokens", "input_tokens"), ("reasoning_output_tokens", "output_tokens")):
                if detail in usage and (type(usage[detail]) is not int or not 0 <= usage[detail] <= usage[total]):
                    valid = False
        item = {"label": self.label, "case_id": case_id, "model": entry["model"],
                "reservation_usd": str(reservation), "usage_valid": bool(valid),
                "standard_rate_estimate_usd": None, "conservative_accounted_usd": str(reservation)}
        if valid:
            standard = estimate(ledger.plan["pricing"], entry["model"], usage["input_tokens"], usage["output_tokens"], conservative=False)
            conservative = estimate(ledger.plan["pricing"], entry["model"], usage["input_tokens"], usage["output_tokens"], conservative=True)
            ledger.accounted += conservative - reservation
            item.update(standard_rate_estimate_usd=str(standard), conservative_accounted_usd=str(conservative))
            if usage["input_tokens"] > entry["input_token_allowance"] or usage["output_tokens"] > entry["max_output_tokens"]:
                ledger.stop_reason = "Reported usage exceeded a reserved token allowance."
        else:
            ledger.stop_reason = "Token usage is missing or invalid; full reservation retained."
        settings = result.provider_settings or {}
        if result.error_kind:
            ledger.stop_reason = "Provider error; no further calls authorized by this monitor."
        elif (result.returned_model != entry["model"] and not (result.returned_model or "").startswith(entry["model"] + "-")):
            ledger.stop_reason = "Provider returned an unexpected model; pricing/experiment needs review."
        elif settings.get("service_tier") != "default":
            ledger.stop_reason = "Provider service tier is missing or differs from the priced default tier."
        elif (settings.get("reasoning") or {}).get("effort") != self.provider.config.reasoning_effort:
            ledger.stop_reason = "Provider reasoning effort differs from the prepared configuration."
        if ledger.accounted > ledger.limit:
            ledger.stop_reason = "Reported conservative cost exceeds the limit; no further calls."
        item["stop_reason_after_call"] = ledger.stop_reason
        ledger.calls.append(item)
        ledger.record({"event": "completed", "at": utc_now(), **item, "execution": asdict(result)})
        return result
