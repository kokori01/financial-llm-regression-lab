# Executed publication validation

Date: November 9, 2026. Runtime application remains 0.2.0 / response contract v2. This preparation changed documentation, Git inclusion rules and offline publication scripts/tests. It did not change benchmark data, prompts, evaluator logic or original measured reports, and made no paid API calls.

## Actual results

| Check | Result |
|---|---|
| Existing environment, full suite | 169 passed; 0 failed; 0 skipped |
| Wheel built from staged-only checkout, test dependencies but no OpenAI SDK | 135 passed; 0 failed; 1 provider module skipped |
| Same isolated wheel environment with optional live SDK | 169 passed; 0 failed; 0 skipped |
| Saved public-response verification | All 24 responses, hashes, paired outcomes and cost estimates verified offline |
| Installed CLI and module replay, outside the source directory | Both succeeded; synthetic baseline 10/12, candidate 3/12 |
| Synthetic regression gate | Expected exit 1 |
| Live dry run without SDK or credentials | Exit 0; no network/generation calls |
| Dependency consistency | No broken requirements |
| Staged Markdown link check | Every local target is staged |
| Staged credential/private-path scan | No credential-shaped strings or local machine paths found |
| Original report/runtime preservation | All 44 pre-preparation file hashes unchanged |

The skipped provider module contains 34 cases that passed with the optional SDK. A module skip is not a failed test. Three added publication tests verify the saved report offline, ensure internal fields are excluded from export without changing measurements, and detect a changed financial response.

## Executed workflow

The source tree was staged locally, then exported with `git checkout-index --all` to a temporary directory. No private reports, credential file, project memory or build products were present in that checkout. No Git commit, remote or publication was needed.

From a fresh Python 3.11 environment, the following sequence was exercised. `<checkout>`, `<wheel>` and `<reports>` denote the temporary staged export, its built wheel and a temporary output directory.

```bash
python -m pip wheel --no-deps <checkout> --wheel-dir <wheel-directory>
python -m pip install -c <checkout>/requirements-tested.txt '<wheel>[test]'
python -m pytest -q <checkout>/tests
python <checkout>/scripts/verify_public_report.py
financial-lab replay --output-dir <reports> --report-name wheel_replay
python -m regression_lab replay --output-dir <reports> --report-name wheel_module
financial-lab replay --output-dir <reports> --report-name wheel_gate --fail-on-regression
python -m pip install -c <checkout>/requirements-tested.txt '<wheel>[test,live]'
python -m pytest -q <checkout>/tests
python -m pip check
```

The exact no-network preview in [LIVE_EXPERIMENT.md](LIVE_EXPERIMENT.md) was also run with the staged pricing file, before installing the SDK. `OPENAI_API_KEY` and `PYTHONPATH` were absent from the isolated validation environment. All generation in provider tests used local HTTP mocks.

The normal existing-environment command was `python -m pytest -q`; it reported `169 passed in 1.08s`. The staged wheel run reported `135 passed, 1 skipped in 0.48s` without the SDK and `169 passed in 1.37s` with it. These are observed test runtimes, not performance guarantees. Final documentation/inventory updates do not change the tested runtime or test files.

## Evidence boundaries

The original audit reproduced 83 passing tests and the prose-related false passes. Contract v2 and live controls expanded the suite to 166 tests before the real experiment. The saved real comparison then completed 24 calls, with both models passing all twelve cases. Publication preparation only rescored the saved responses.

The public record retains the original engine hash and thirteen frozen benchmark/evaluator/prompt/resource hashes. It can be checked without the private source record. The source-record SHA-256 identifies the privately retained original; it does not independently authenticate provider origin. Recorded costs remain estimates, and no billing invoice was retrieved. No claim of broad model reliability follows from this single small run.
