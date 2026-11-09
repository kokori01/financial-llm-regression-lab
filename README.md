# Financial LLM Regression Lab

A Python CLI for testing a financial question-answering component after a model or prompt change. Twelve fixed cases use a small, manually verified snapshot of Apple's FY2025 Form 10-K. The evaluator checks structured claims, calculations, units, fiscal periods, supporting citations, abstention and two specified instruction attacks.

The repository contains **two different kinds of evidence**:

| Evidence | Baseline | Candidate | Regressions | Meaning |
|---|---:|---:|---:|---|
| Authored synthetic replay | 10/12 | 3/12 | 8 | Detection of deliberately inserted defects |
| One live model comparison, 2026-11-09 | 12/12 | 12/12 | 0 | Observed behavior of two models on these cases |

The live comparison used `gpt-5.6-terra` and `gpt-6.1-terra` with the same `strict-v2` prompt and low reasoning effort. All 24 responses completed without provider errors. The visible answers were identical. **This does not establish model equivalence, superiority or production reliability.**

[Public live report](reports/public/live_model_comparison_20261109.md) · [Responses and metadata in JSON](reports/public/live_model_comparison_20261109.json) · [Interpretation](docs/LIVE_RESULTS_20261109.md)

This independent project by Koray Tümay was motivated by Reflexivity's public article, [The Model Upgrade Problem](https://reflexivity.com/en/blog/the-model-upgrade-problem), and the need to revalidate application contracts after model changes. There is no affiliation with Reflexivity or claim to reproduce its systems.

## Run offline

Python 3.11 or later is required. From the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -c requirements-tested.txt -e '.[test]'
financial-lab replay --report-name local_replay
python scripts/verify_public_report.py
python -m pytest -q
```

Installation requires package access. Replay and public-report verification then run without credentials, an OpenAI SDK or network access. `python -m regression_lab replay --report-name local_module_replay` is the equivalent module entry point.

The verifier reconstructs input packets, checks source and prompt hashes, rescores the 24 saved responses, and recalculates estimated costs. It does not call a model. The public extract preserves the original response strings and measurements; operational identifiers and private execution records are excluded. Its source-record hash identifies the privately retained original, not independent provider attestation.

For the provider tests using local HTTP mocks:

```bash
python -m pip install -c requirements-tested.txt -e '.[test,live]'
python -m pytest -q
```

The runtime depends only on Pydantic. Tested versions and validation commands are in [requirements-tested.txt](requirements-tested.txt) and [validation](docs/VALIDATION.md). Mocked provider tests do not make paid requests.

## What is checked

A model returns exactly one JSON object with `status`, `value`, `unit`, `period` and `citations`. All fields are required; extra fields, numeric strings, duplicate keys, nonfinite numbers, fences and surrounding prose fail. An answered claim needs a numeric value and period. Abstention requires null value/period, `not_applicable` unit and no citations.

```json
{"status":"answered","value":6.43,"unit":"percent","period":{"basis":"fiscal","year":2025,"start":"2024-09-29","end":"2025-09-27"},"citations":["AAPL_FY2025_SALES","AAPL_FY2024_SALES"]}
```

The live API did **not** enforce Structured Outputs. The JSON schema and instructions were in the prompt; parsing and validation happened locally. Schema results therefore measure prompted compliance in the saved responses.

Numbers are compared with reviewed gold values using inclusive absolute Decimal tolerances. Percentages use two-decimal `ROUND_HALF_UP` gold and a 0.1 percentage-point tolerance; billions use three decimals and a 0.0005 billion tolerance; direct million-dollar figures are exact. Units and fiscal periods are checked separately.

Citation support is checked against the supplied records: every cited ID must be in the packet and relevant to the required metric, company, fiscal year, dates and unit. All calculation operands must be cited, and their values must reproduce the claim within tolerance. This is bounded evidence validation, not arbitrary-language citation entailment.

| Case | Scenario | Expected result |
|---|---|---|
| C01 | FY2025 sales | 416161 USD millions |
| C02 | Sales growth over FY2024 | 6.43% |
| C03 | Gross margin percentage | 46.91% |
| C04 | Operating margin percentage | 31.97% |
| C05 | Fiscal versus calendar year | FY2025, 2024-09-29 to 2025-09-27 |
| C06 | Millions to billions | 416.161 USD billions |
| C07 | Supporting source for net income | 112010 USD millions |
| C08 | Reject irrelevant/wrong-year citations | Gross margin, 195201 USD millions |
| C09 | FY2027 sales absent from packet | Abstain |
| C10 | Adjusted EBITDA unsupported by packet | Abstain |
| C11 | User attempts format override | Correct sales claim under the contract |
| C12 | Synthetic attachment requests fabricated value | Correct supported sales claim |

C09/C10 test the packet's evidence boundary, regardless of facts available elsewhere. C12's attack is synthetic, separate from the verified filing content. See the [case-by-case methodology review](docs/METHODOLOGY_REVIEW.md).

## Why the output interface is narrow

An earlier evaluator could pass correct numeric fields accompanied by false prose, including a claim that Apple sold nothing. Three independently written probes reproduced that defect. Contract v2 removes model-written prose and adds a typed period. The application renders a short display sentence only after all applicable checks pass; abstention wording is application-owned.

This is a backward-incompatible interface constraint, not a general semantic-faithfulness solution. An `answer` field is invalid regardless of whether its wording is true. General prose semantics remain `not_evaluated`. The [decision record](docs/ANSWER_CONTRACT.md), [before probes](reports/audit_before_semantic_probes.json) and [after probes](reports/audit_after_semantic_probes.json) document the tradeoff. Archived v1 resource files remain for inspection; scores across contract versions are not directly comparable model measurements.

## Source and expected answers

The frozen source is Apple's FY2025 Form 10-K, filed October 31, 2025, accession `0000320193-25-000079`. Seven facts were transcribed from Item 8, Consolidated Statements of Operations, page 29; fiscal-year interpretation comes from Note 1, page 34. FY2024 figures are comparatives in that same filing.

- [Apple filing](https://d18rn0p25nwr6d.cloudfront.net/CIK-0000320193/c636d8a7-8025-47d2-9b13-bcf5465343b3.html)
- [SEC filing index](https://www.sec.gov/Archives/edgar/data/320193/0000320193-25-000079-index.htm)
- [Evidence snapshot](src/regression_lab/resources/data/sec_facts_snapshot.json) and [source re-verification](reports/source_reverification.json)
- [Case definitions and gold](src/regression_lab/resources/data/cases.json)

The loader reconciles gold with explicit formulas over the source facts. Separate tests use rational arithmetic on source-transcribed literals. Fixture defect labels never determine evaluation outcomes. Human source review remains necessary; the project does not retrieve filings or verify arbitrary documents at runtime.

## Architecture and regression detection

The runner constructs identical question/evidence packets for baseline and candidate. Replay returns authored response strings; the optional live adapter returns provider output. Both use the same evaluator. Model input contains evidence and contract instructions, not gold fields or fixture defect annotations.

| Module | Responsibility |
|---|---|
| `schemas.py`, `dataset.py` | Strict contracts, packaged facts/cases and gold reconciliation |
| `evaluators.py`, `answers.py` | Deterministic checks and display rendering after success |
| `runner.py`, `comparison.py` | Shared execution and case-ID pairing |
| `reporting.py` | Markdown/JSON reports with outcomes, errors and provenance |
| `prompts.py`, `providers.py` | Versioned prompts and optional OpenAI adapter |
| `budget.py`, `credentials.py`, `cli.py` | Spending monitor, explicit private key loading and commands |

A regression is baseline pass → candidate fail; an improvement is fail → pass. Shared failures are listed separately. Execution errors make a pair non-comparable. Refusals and incomplete generated outputs fail the output contract. Checks that cannot run after a schema failure are marked not evaluated, not awarded passes.

There is no retrieval pipeline, model training or autonomous agent workflow. [The walkthrough](docs/PROJECT_WALKTHROUGH.md) explains the design in more detail.

## Live experiment and cost interpretation

The saved experiment used one response per case/model, baseline then candidate, low reasoning effort, a 4096-token output limit including reasoning, zero retries and the default tier. Returned IDs matched requested IDs. The model names are aliases rather than pinned dated snapshots.

Reported usage was 59,608 input and 1,973 output tokens, including 489 reasoning tokens. At rates recorded on November 9, 2026, the standard-rate estimate was **$0.106641**; conservative accounting using higher input rates and a margin was **$0.2648349**. Neither is an exact invoice. The candidate's standard estimate was lower; this single trial does not establish a stable cost or latency advantage.

The [live workflow](docs/LIVE_EXPERIMENT.md) explains the exact settings, secure local setup, no-network preview and spending controls. The client monitor is not a provider-enforced dollar cap. New live execution requires an explicit paid-call flag and a separately reviewed budget; verification of saved evidence does not.

## Reports and exit codes

[Included evidence](reports/README.md) distinguishes synthetic fixtures from the public live extract. Original live records, private journals, local credentials and project memory are excluded from Git. Public links target explicitly included files.

Exit `0` means execution/report generation succeeded; `1` means regressions were found when `--fail-on-regression` is enabled; `2` means a configuration/report error or non-comparable execution failure. For example, the synthetic gate intentionally exits `1`:

```bash
financial-lab replay --report-name local_gate --fail-on-regression
```

Use fresh names: replay and unbudgeted reports can overwrite the same name; budgeted live execution refuses existing report/journal names. Public evidence is a separate, reviewed extract and is not the default report destination.

## Limits

One company, one filing, twelve overlapping cases and one trial per model provide no statistical generalization. Fixed ordering, sampling and unpinned aliases limit repeatability of future generations. Public filing data may have appeared in training corpora. Passing two attacks does not establish broad injection resistance, and the structured interface does not evaluate open-ended financial explanations.

The all-pass run shows no observed migration regression on this set. A separately designed held-out evaluation and repeated/order-varied trials would be needed for stronger conclusions. No such additional experiment is claimed here.

See [publication contents and repository metadata](docs/PUBLICATION.md) for the reviewed public file set.
