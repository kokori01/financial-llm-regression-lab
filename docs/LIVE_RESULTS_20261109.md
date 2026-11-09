# First live comparison — results and limits

One saved experiment on November 9, 2026 compared `gpt-5.6-terra` with `gpt-6.1-terra` on the existing twelve cases. Both passed 12/12. There were no regressions, improvements, shared failures or provider errors. All 24 generation calls completed with usage metadata, and all twelve visible response strings were identical across models.

This document describes the same measured results as the privately retained original. The repository includes a minimal public extract, generated without rerunning inference or changing the benchmark.

## What was observed

Both models passed strict JSON/schema checks on 12/12 cases; numeric, unit and fiscal-period checks on 10/10 answerable cases; abstention on 2/2 missing-evidence cases; and both specified instruction-resistance probes. Citation checks passed for all cases, including empty citation lists on abstention. The numeric responses matched the reviewed gold values exactly, not merely within tolerance.

Both used `strict-v2`, low reasoning effort, 4096 maximum output tokens, default tier, no tools, `store=False`, a 45-second timeout and zero retries. The same input packet reached each configuration, baseline first for each case. JSON compliance was prompted and checked locally, not API-enforced. Reported effective settings were low effort, standard reasoning mode, temperature 1.0 and top_p 0.98; sampling parameters were omitted from requests.

## Usage and estimated cost

| Measurement | gpt-5.6-terra | gpt-6.1-terra |
|---|---:|---:|
| Input tokens | 29,804 | 29,804 |
| Output tokens, including reasoning | 1,052 | 921 |
| Reasoning tokens within output | 310 | 179 |
| Reported cached input tokens | 0 | 0 |
| Standard-rate estimated USD | 0.072232 | 0.034409 |
| Conservative accounting USD | 0.17780840 | 0.087026500 |
| Summed request latency, seconds | 24.190 | 24.443 |

Total standard-rate estimate: **$0.106641**. Conservative accounting: **$0.2648349**, using higher input-price allowances and a 10% margin. Rates and assumptions are recorded in the [dated pricing file](live_pricing_2026-11-09.json) and public report. These are calculated estimates, not an invoice. The standard calculation does not identify cache-write premiums separately; no cache-read discount was credited. Exact billing was not retrieved.

The candidate's standard-rate estimate was about 52.4% lower in this run, largely because of its recorded prices. Summed latency was similar. A single trial does not establish a stable cost, speed or reasoning-efficiency advantage.

## What the evidence supports

The recorded configuration completed a real provider integration and migration check with no observed regression on this set. The all-pass result offers little discrimination between models. It does not establish general equivalence, statistical superiority, production readiness, arbitrary citation faithfulness or broad prompt-injection resistance.

The dataset covers one filing with overlapping cases. There is one sample per configuration/case, fixed ordering, sampling and unpinned model aliases. Public facts may have appeared in training corpora. Future generations may differ even when the saved inputs and scoring code are reproduced.

Synthetic replay is separate: baseline 10/12 and candidate 3/12, with eight deliberately created regressions and one improvement. Those fixtures demonstrate detection of known defects; they are not measurements of either live model and must not be blended with the live results.

## Public evidence and verification

- [Public Markdown report](../reports/public/live_model_comparison_20261109.md)
- [Public JSON: all saved response strings, measurements and provenance](../reports/public/live_model_comparison_20261109.json)
- [Offline verification script](../scripts/verify_public_report.py)
- [Methodology](METHODOLOGY_REVIEW.md) and [execution settings](LIVE_EXPERIMENT.md)

The public JSON retains input and frozen-source hashes, exact prompt/schema, requested and returned model IDs, effective settings, usage, latency and per-case checks. It omits provider response IDs, account-access checks, authorization records, private journals and local configuration. The original measured files remain unchanged outside the public Git index.

`python scripts/verify_public_report.py` reconstructs the inputs and rescores all 24 saved responses without API access. This verifies consistency of the recorded evidence and code; it does not independently authenticate provider origin or recreate the model run. No scoring rules or benchmark cases were changed after observing the results.
