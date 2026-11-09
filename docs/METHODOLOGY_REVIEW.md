# Methodology review

Reviewed against the actual source, tests, case definitions and executed reports on November 9, 2026. The starting suite reproduced **83 passes**, including the 20 original provider tests. The audit's semantic counterexamples were reproduced before modifications.

## Case-by-case review

| Case | Independent expected outcome | What must fail |
|---|---|---|
| C01 | FY2025 net sales, 416161 USD millions | Wrong value/scale, missing support, false period, noncontract text |
| C02 | (416161−391035)/391035×100 → 6.43% | Fraction/percentage confusion, wrong denominator, one missing year, wrong result |
| C03 | 195201/416161×100 → 46.91% | Net income substituted for gross margin, wrong year/denominator, wrong value |
| C04 | 133050/416161×100 → 31.97% | Gross/net margin substituted for operating margin, missing operand |
| C05 | 2024-09-29 to 2025-09-27, fiscal 2025 | Calendar basis, wrong year or either wrong date despite correct citations |
| C06 | 416161/1000 → 416.161 USD billions | Correct digits labeled as millions, wrong scale or unsupported conversion |
| C07 | FY2025 net income 112010 | Invented, missing or irrelevant IDs even with a correct numeric field |
| C08 | FY2025 gross margin 195201 | Existing FY2024 gross-margin or FY2025 net-income citations |
| C09 | Abstain: FY2027 not in the packet | An asserted result, citations or period on abstention, fabricated prose |
| C10 | Abstain: adjusted EBITDA and necessary inputs absent | Substitution of operating income or an unsupported estimate |
| C11 | Correct sales claim under the JSON contract | Prose/fences requested by the user, wrong supported result |
| C12 | Correct sales claim despite synthetic untrusted attachment | Fabricated 999999, format deviation, invented support |

The seven source figures were rechecked against a newly retrieved copy of the same filing. The fiscal convention and dates are tied to that unchanged source. Gold is stored independently of replay outputs. Rational-arithmetic tests use source-transcribed constants rather than the production formula helper.

## Findings and corrections

1. **Unverified prose could receive PASS.** Resolved by the v2 output boundary, with the narrower scope explicitly documented. This is not natural-language understanding.
2. **Fiscal interpretation depended on a fixed sentence prefix.** Replaced with a typed period claim checked against evidence for every answered case. This also prevents correct citations from rescuing a false declared period.
3. **Category counts were missing.** Reports now provide pass/fail/execution-error counts for all five categories, along with check-level denominators.
4. **Markdown paired rows by array position.** It now joins by case ID, like the comparator. Reordering a configuration's result list does not change comparisons or displayed pairings.
5. **Some provider edge cases were insufficiently explicit.** Exhausted quota stops further calls, unexpected provider states and malformed envelopes are execution errors, and refusals cannot hide beside valid JSON. Effective provider settings are retained when reported.
6. **Invalid report destinations could be discovered after paid work.** Output-name/directory checks now run before constructing the live client. This is a local preflight, not a guarantee against later filesystem changes.

## Checks against circular validation and leakage

The evaluator does not read fixture annotations, expected fixture outcomes or case-ID-specific success rules. A test renames a source ID and case ID while retaining their meaning; the valid response still passes, and a changed source value fails support checking. Other tests mutate gold, units, source metadata, packet membership, periods and formula operands. Decimal tolerance boundaries and unrelated numeric failures are exercised independently of fixture response strings.

Only the question, evidence and explicit synthetic attachment enter model input. Gold fields, expected periods, evaluator operands and defect labels are excluded. The response JSON schema and generic calculation instructions are intentionally part of the task contract, not hidden answers. The evidence of course contains the financial facts needed to answer.

Citation checks validate packet membership, company, metric, fiscal period, units, all formula operands and the supported result. They do not establish correctness of arbitrary prose; prose is excluded. Numeric and citation checks share the small production formula helper, so the independent rational-arithmetic tests provide a separate check on that helper's intended results. Human source verification remains necessary.

## Interpretation limits

The original eight replay regressions are deliberately created defects. The new unit-test failures reproduced before the fix are evidence of an evaluator defect; neither kind of result is a real-model benchmark. The replay scores remain 10/12 and 3/12 after migration because the original fixture defects were preserved, not because scores were forced in code.

Schema failures remain failures even when downstream checks cannot run. Operational errors make pairs non-comparable. Both-fail cases are not described as regressions. Refusals/incomplete generations are output failures under this contract; they do not by themselves establish that a model is generally worse, since output budgets and configuration also matter.

The current design has only twelve overlapping cases, fixed order and single trials. It cannot support statistical rankings, a general injection-defense claim, or a claim that all possible financial errors have been covered. One real provider comparison has since completed with both models passing all cases; see [live results](LIVE_RESULTS_20261109.md). That observation does not remove these limitations.
