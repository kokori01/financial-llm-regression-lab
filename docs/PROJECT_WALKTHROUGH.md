# Understanding the project

Think of the system as a small acceptance-test rig for one component that turns a financial question into a structured answer. The component might use one model today and another tomorrow. The rig asks whether the replacement still meets the same application contract.

## Data comes first

The evidence snapshot contains seven verified Apple filing facts. Each number keeps its meaning: metric, currency scale, fiscal period and source location. A second file defines twelve questions and their independently reviewed expected outcomes. Two questions intentionally lack evidence, so their correct outcome is abstention.

The answers are not whatever the current model happens to say. For example, growth is independently established as (416161−391035)/391035×100, approximately 6.43 percent. The model has to reach that result from the packet.

## Execution is replaceable; judging is shared

The runner builds one input packet per case and sends the identical bytes to baseline and candidate. In replay, an adapter returns an explicitly authored synthetic string. In live mode, the OpenAI adapter would return the actual provider output. Both travel through the same evaluator.

This separation is useful: the evaluator can be demonstrated and tested without money, credentials or network access. It also prevents a special lenient grading path for live responses. The recorded input hashes make accidental input differences visible.

## What evaluation means

First, strict parsing asks whether the entire output is the required JSON object. The system does not cut JSON out of prose or repair malformed output, because the downstream interface is exactly what is being tested.

Next, Pydantic checks types and relationships between fields. A numeric string is not a number. Abstention cannot contain a financial value or citations. A period must have valid dates.

The evaluator then checks the question-specific claims. It compares the number with a gold value under a documented absolute tolerance, verifies the unit and fiscal period, and checks source support. Citing a real FY2024 source does not justify a FY2025 result. A percentage requires citations for both operands, and those operands must recompute the claimed value.

## Why the model no longer writes the display sentence

The audit showed that checking a correct numeric field did not make the accompanying English true. A model could provide 416161 in the numeric field and say that Apple sold nothing. Trying to fix this with a few keywords would not be trustworthy.

The revised component accepts structured claims only. When all checks pass, the application writes a simple sentence from those checked values and trusted query metadata. When evidence is missing, it writes a fixed statement about that limitation. Failed output remains in the audit report but receives no approved display answer.

This is an engineering boundary choice: reduce what the component is allowed to promise until the promise can be checked. It does not solve general language evaluation. If the product needed rich narrative explanations, a separate review or evaluation design would be necessary.

## How a regression is detected

Compare the two outcomes for the same case:

| Baseline | Candidate | Interpretation |
|---|---|---|
| Pass | Fail | Regression |
| Fail | Pass | Improvement |
| Fail | Fail | Shared failure |
| Pass | Pass | Shared pass |
| Either has an execution error | Any | Not comparable |

A network timeout does not tell us whether the model would have answered correctly, so it is kept out of quality regressions. A completed model response with prose around JSON does violate the component contract, so it is a model-output failure. An incomplete generation is also unusable under this contract, although the configured output budget may explain it.

## What you can defend to a senior engineer

The project demonstrates source provenance, strict interfaces, independent expectations, deterministic checking, failure classification, provider isolation and reproducible reports. You can also explain the tradeoff made after finding a real evaluator weakness.

The synthetic score difference is deliberately manufactured and is not a selling point about any model. Its value is showing that the harness detects known failure modes. That next experiment has now been executed with the v2 contract, prompts and evidence fixed: both real models passed all twelve cases, with zero observed regressions. This supports compatibility on the small set but also reveals its limited ability to distinguish these models. See [the real-run interpretation](LIVE_RESULTS_20261109.md).
