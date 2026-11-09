# Live workflow and recorded configuration

The included live evidence comes from one completed experiment on November 9, 2026. See [results](LIVE_RESULTS_20261109.md) and the [public record](../reports/public/live_model_comparison_20261109.json). Publication preparation does not rerun it.

## Recorded settings

| Setting | Baseline | Candidate |
|---|---|---|
| Requested / returned model | gpt-5.6-terra | gpt-6.1-terra |
| Prompt | strict-v2 | strict-v2 |
| Response contract | v2 structured claims | v2 structured claims |
| Reasoning effort | low | low |
| Maximum output tokens, including reasoning | 4096 | 4096 |
| Temperature / top_p | omitted | omitted |
| Timeout | 45 seconds | 45 seconds |
| Retries | 0 | 0 |
| Tier / endpoint | default / Responses | default / Responses |
| Tools / storage | none / store=False | none / store=False |
| Generation calls | 12 | 12 |

The API was asked for plain-text output. JSON schema was in the prompt and validated locally. Both configurations received identical serialized packets. Ordering was baseline then candidate per case. Equal effort did not imply equal reasoning-token use. Model aliases are not pinned dated snapshots; public availability does not prove access for another account.

## No-network preview

From an installed checkout, this does not need an API key or the OpenAI SDK:

```bash
financial-lab live \
  --baseline-model gpt-5.6-terra --candidate-model gpt-6.1-terra \
  --baseline-prompt strict-v2 --candidate-prompt strict-v2 \
  --omit-temperature --reasoning-effort low --max-output-tokens 4096 \
  --max-retries 0 --budget-usd 2 \
  --pricing-file docs/live_pricing_2026-11-09.json --dry-run
```

The price file is historical experiment metadata, not a promise of current prices. Recheck model access, supported settings and pricing before any new paid execution. Using different prompts tests prompt migration; changing both model and prompt cannot isolate the cause.

## Credentials and paid execution

The optional `.[live]` extra installs the SDK. Credentials come from `OPENAI_API_KEY`, or an explicitly selected owner-only file via `--env-file`. To create that local file, run `python scripts/configure_api_key.py` in your own interactive Terminal. It uses hidden input and exclusive creation with permissions 600; it does not overwrite an existing file. `.env` files, keys and project memory are ignored by Git.

`--preflight-only` retrieves model metadata and makes no generation call. Retrieval does not establish generation-parameter compatibility. Actual generation requires `--allow-paid-api`; it should only be supplied after separate approval of a specific new experiment and budget. No paid command needs to run to reproduce the published evaluation of saved responses.

## Spending control and interpretation

The optional shared budget monitor requires zero SDK retries. It reserves each full call before dispatch and checks usage, returned model, tier and effort afterward. Missing/invalid usage, request errors or incompatible metadata stop both configurations. An uncertain call retains its full reservation; it is not retried automatically. A durable local journal records reservations and results, and reused report names are refused.

This is not a provider-enforced hard dollar cap. It cannot undo a server-side charge or govern unrelated account activity. Output limits include reasoning. Timeouts, failed requests or incomplete output can consume resources. Cost reports are estimates rather than invoices.

For the recorded inputs, instructions plus input text totaled 89,837 UTF-8 bytes per configuration. The planning allowance was one token per byte plus 1,024 framing tokens per call: 102,125 input tokens per model, with 49,152 maximum output tokens per model. This was a deliberately loose allowance, not measured tokenization. An input-price ceiling of $5/$2.50 per million for baseline/candidate, plus a 10% margin, produced a full-reservation estimate of $1.76167365. The measured usage and resulting cost estimates are in the public results; the planning allowance was not money spent.

Keep future runs separate. Do not alter the existing cases, saved responses or scoring rules to make an observed comparison more dramatic. Refusals and incomplete outputs fail the component contract; provider errors make pairs non-comparable.
