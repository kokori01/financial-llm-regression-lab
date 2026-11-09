# Repository metadata and public contents

Recommended repository name: **financial-llm-regression-lab**.

Recommended GitHub description:

> Python regression harness for financial QA, with strict validation, synthetic replay, and a documented live model comparison.

This is a local publication candidate. No GitHub repository, remote, commit, push or publication is created by preparation. The initial Git index is reviewed separately from private working files.

## Evidence policy

The public live extract retains actual responses, outcomes, model/prompt settings, token usage, latency, historical cost assumptions and reproducibility hashes. It omits provider response IDs, account-access records, private authorization and execution journals. Original measured files are not rewritten. Internal project memory, local configuration, credentials, caches and build products are excluded.

The `.gitignore` report allowlist is intentional: only named reviewed report files can be added by a normal `git add`. Git ignore rules are not an access-control system; force-adding a private file would bypass them. Review the staged list before any future publication.

## Exact public file list

The reviewed Git index contains **55 files**. Paths are relative to the repository root.

```text
.gitignore
README.md
docs/ANSWER_CONTRACT.md
docs/LIVE_EXPERIMENT.md
docs/LIVE_RESULTS_20261109.md
docs/METHODOLOGY_REVIEW.md
docs/PROJECT_WALKTHROUGH.md
docs/PUBLICATION.md
docs/VALIDATION.md
docs/live_pricing_2026-11-09.json
pyproject.toml
reports/README.md
reports/audit_after_semantic_probes.json
reports/audit_before_semantic_probes.json
reports/public/live_model_comparison_20261109.json
reports/public/live_model_comparison_20261109.md
reports/sample_report_v2.json
reports/sample_report_v2.md
reports/source_reverification.json
requirements-tested.txt
scripts/configure_api_key.py
scripts/export_public_report.py
scripts/verify_public_report.py
src/regression_lab/__init__.py
src/regression_lab/__main__.py
src/regression_lab/answers.py
src/regression_lab/budget.py
src/regression_lab/cli.py
src/regression_lab/comparison.py
src/regression_lab/credentials.py
src/regression_lab/dataset.py
src/regression_lab/evaluators.py
src/regression_lab/prompts.py
src/regression_lab/providers.py
src/regression_lab/reporting.py
src/regression_lab/resources/data/cases.json
src/regression_lab/resources/data/cases_v1.json
src/regression_lab/resources/data/sec_facts_snapshot.json
src/regression_lab/resources/fixtures/baseline_responses.json
src/regression_lab/resources/fixtures/baseline_responses_v1.json
src/regression_lab/resources/fixtures/candidate_responses.json
src/regression_lab/resources/fixtures/candidate_responses_v1.json
src/regression_lab/runner.py
src/regression_lab/schemas.py
tests/conftest.py
tests/test_answer_boundary.py
tests/test_budget.py
tests/test_credentials.py
tests/test_evaluators.py
tests/test_methodology.py
tests/test_providers.py
tests/test_publication.py
tests/test_regressions.py
tests/test_runner.py
tests/test_schema.py
```

## Verification

A checkout containing only these staged files built and installed successfully. Its full suite passed 169 tests; without the optional OpenAI SDK, 135 passed and one provider-test module was skipped. All public document links resolved inside the staged set, and saved live evidence was verified offline. See [validation](VALIDATION.md).
