"""Spending controls use fake execution only; no requests to a provider."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from regression_lab.budget import BudgetedProvider, BudgetLedger, budget_plan, load_pricing
from regression_lab.dataset import case_input
from regression_lab.providers import LiveConfig
from regression_lab.runner import Execution


@pytest.fixture
def setup(benchmark):
    snapshot, cases = benchmark
    configs = [LiveConfig(m, "strict-v2", None, 4096, 45, 0, "low")
               for m in ("gpt-5.6-terra", "gpt-6.1-terra")]
    prices = load_pricing(Path(__file__).parents[1] / "docs/live_pricing_2026-11-09.json")
    plan = budget_plan(snapshot, cases, configs, prices, "2")
    return snapshot, cases, configs, plan


class FakeProvider:
    mode = "live"

    def __init__(self, label, config, changes=None):
        self.label, self.config = label, config
        self.configuration = config.describe()
        self.calls = 0
        self.changes = changes or {}

    def execute(self, case_id, text):
        self.calls += 1
        args = dict(raw_response="{}", started_at="test", latency_ms=1,
                    requested_model=self.config.model, returned_model=self.config.model,
                    generation_call_initiated=True,
                    usage={"input_tokens": 2000, "output_tokens": 100, "total_tokens": 2100},
                    provider_settings={"service_tier": "default", "reasoning": {"effort": "low"}})
        return Execution(**(args | self.changes))


def test_full_plan_conservative_arithmetic(setup):
    _, _, _, plan = setup
    assert len(plan["calls"]) == 24 and plan["within_budget"] and not plan["hard_cap"]
    assert sum(c["request_text_utf8_bytes"] for c in plan["calls"][:12]) == 89837
    # Independent literals: 102125 input allowance/model; 49152 output/model.
    expected = (Decimal(102125) * Decimal('7.5') + Decimal(49152) * 17) * Decimal('1.1') / 1000000
    assert Decimal(plan["planned_maximum_estimate_usd"]) == expected == Decimal('1.76167365')


def test_usage_accounting_shared_between_models_and_durable_journal(setup, tmp_path):
    snapshot, cases, configs, plan = setup
    journal = tmp_path/'calls.jsonl'
    with journal.open('w') as stream:
        ledger = BudgetLedger(plan, stream)
        for label, config in zip(('baseline', 'candidate'), configs):
            provider = BudgetedProvider(FakeProvider(label, config), ledger)
            result = provider.execute('C01', case_input(cases[0], snapshot))
            assert result.error_kind is None
    summary = ledger.summary()
    assert len(journal.read_text().splitlines()) == 4
    assert summary['initiated_calls'] == 2 and summary['all_initiated_calls_have_valid_usage']
    assert Decimal(summary['standard_rate_estimate_usd']) == Decimal('0.0077')
    assert Decimal(summary['accounted_conservative_usd']) == Decimal('0.01837')
    assert summary['stop_reason'] is None


def test_reserve_next_full_call_not_just_cost_so_far(setup):
    snapshot, cases, configs, plan = setup
    plan['budget_usd'] = '0.01'
    ledger = BudgetLedger(plan)
    inner = FakeProvider('baseline', configs[0])
    result = BudgetedProvider(inner, ledger).execute('C01', case_input(cases[0], snapshot))
    assert inner.calls == 0 and result.error_kind == 'budget_guard_stopped'


@pytest.mark.parametrize('changes', [
    {'usage': None},
    {'usage': {'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 9}},
    {'usage': {'input_tokens': -1, 'output_tokens': 1, 'total_tokens': 0}},
    {'usage': {'input_tokens': True, 'output_tokens': 1, 'total_tokens': 2}},
    {'usage': {'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2, 'cached_input_tokens': 3}},
    {'usage': {'input_tokens': 1, 'output_tokens': 4097, 'total_tokens': 4098}},
    {'usage': {'input_tokens': 10000, 'output_tokens': 1, 'total_tokens': 10001}},
    {'error_kind': 'timeout', 'usage': None},
    {'returned_model': 'different-model'},
    {'provider_settings': {'service_tier': 'priority', 'reasoning': {'effort': 'low'}}},
    {'provider_settings': {'service_tier': 'default', 'reasoning': {'effort': 'high'}}},
])
def test_uncertainty_stops_both_configurations_without_retry(setup, changes):
    snapshot, cases, configs, plan = setup
    ledger = BudgetLedger(plan)
    first = FakeProvider('baseline', configs[0], changes)
    second = FakeProvider('candidate', configs[1])
    text = case_input(cases[0], snapshot)
    BudgetedProvider(first, ledger).execute('C01', text)
    result = BudgetedProvider(second, ledger).execute('C01', text)
    assert first.calls == 1 and second.calls == 0
    assert ledger.stop_reason and result.error_kind == 'budget_guard_stopped'
    if changes.get('usage', 'present') is None:
        assert ledger.accounted == Decimal(plan['calls'][0]['reservation_usd'])


@pytest.mark.parametrize('mutation', ['input', 'prompt', 'duplicate'])
def test_unplanned_or_repeated_requests_are_blocked(setup, mutation):
    snapshot, cases, configs, plan = setup
    ledger = BudgetLedger(plan)
    inner = FakeProvider('baseline', configs[0])
    guarded = BudgetedProvider(inner, ledger)
    text = case_input(cases[0], snapshot)
    if mutation == 'input': text += 'changed'
    if mutation == 'prompt': inner.config = replace(configs[0], prompt_id='explicit-v3')
    if mutation == 'duplicate': guarded.execute('C01', text)
    result = guarded.execute('C01', text)
    assert result.error_kind == 'budget_guard_stopped'
    assert inner.calls == (1 if mutation == 'duplicate' else 0)


def test_retries_rejected_before_execution(setup):
    snapshot, cases, configs, plan = setup
    with pytest.raises(ValueError, match='zero SDK retries'):
        budget_plan(snapshot, cases, [replace(configs[0], max_retries=1), configs[1]], plan['pricing'], '2')
