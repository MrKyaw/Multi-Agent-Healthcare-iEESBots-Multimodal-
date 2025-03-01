# Testing

> **Scope:** the tests verify the deterministic `ieesbots` governance package with
> synthetic data. They do **not** validate clinical safety, diagnostic accuracy,
> usability, fairness, or regulatory fitness. Not a medical device.

## How to run

From the repository root:

```bash
python3 -m pytest -q
python3 -m pytest --cov=ieesbots --cov-branch --cov-report=term-missing
```

Optional conveniences:

```bash
make test
make coverage
make demo
```

Requirements: Python 3.10+, `pytest`, and `pytest-cov` for coverage. The runtime
package itself has no third-party dependencies.

## Measured results

Local machine: **Python 3.12.8 on macOS**. Recorded during this upgrade.

```text
$ python3 -m pytest -q
133 passed in 0.44s
```

```text
$ python3 -m pytest --cov=ieesbots --cov-branch --cov-report=term-missing

Name                         Stmts   Miss Branch BrPart    Cover   Missing
--------------------------------------------------------------------------
ieesbots/__init__.py            16      0      0      0  100.00%
ieesbots/__main__.py             4      0      2      0  100.00%
ieesbots/agents.py              97      0     28      0  100.00%
ieesbots/audit.py               48      0      8      0  100.00%
ieesbots/casefile.py            51      0     16      0  100.00%
ieesbots/cli.py                 42      0      8      0  100.00%
ieesbots/clinical_rules.py      38      0     18      0  100.00%
ieesbots/consent.py             21      0      2      0  100.00%
ieesbots/contracts.py           57      0      0      0  100.00%
ieesbots/exceptions.py          17      0      0      0  100.00%
ieesbots/models.py             178      0     10      0  100.00%
ieesbots/orchestrator.py        79      0     10      0  100.00%
ieesbots/policy.py              28      0     16      0  100.00%
ieesbots/redaction.py           62      0      6      0  100.00%
ieesbots/router.py              55      0     28      0  100.00%
--------------------------------------------------------------------------
TOTAL                          793      0    152      0  100.00%
Required test coverage of 100.0% reached. Total coverage: 100.00%
```

The gate is configured in `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["ieesbots"]
branch = true

[tool.coverage.report]
fail_under = 100
```

`fail_under = 100` means a regression in line **or** branch coverage fails CI.

## What is covered

| Area | Representative assertions |
|---|---|
| Models & serialization | Validation boundaries, role labels, plan properties, policy reasons, summary rendering, JSON shape |
| PHI redaction | All five identifier kinds, repeated-value token stability, round-trip detokenization, unknown tokens, empty input, custom patterns |
| Consent gate | Granted scope, missing scope denial with reason, plan-wide authorization, unknown role, extra scopes |
| Routing | Baseline, every flag trigger individually, all flags together, stable priority order, rationale text |
| Clinical rules | All red-flag terms, structured flags, allergy family/containment matching, empty entries, polypharmacy thresholds |
| Policy engine | `ALLOW`, `ESCALATE`, `BLOCK`; red flag with/without evidence; block dominance over escalation; pediatric/pregnancy/mental-health triggers |
| Audit | Valid chain, deterministic hashing, details tamper, previous-hash tamper, index tamper, empty chain, `verify_or_raise` |
| Agents | Critical/urgent/semi-urgent/routine triage, complete/fallback/missing evidence, conflict/polypharmacy/clear medication, human packet with/without findings |
| Summarizer | Full context, absent optional agents, unknown evidence ID, missing-packet inconsistency, citations and disclaimers |
| Orchestrator | Demo escalation, clean completion, safety block, consent block, PHI redaction, dependency injection, fixed clock, ledger links, serializability |
| Case file | Minimal/full documents, non-mapping input, missing fields, bad age, bad flags, unknown flags/scopes, malformed evidence, file errors |
| CLI | `--help`, no args, text demo, JSON demo, case file, blocked exit code, invalid input exit codes, `python -m` entry point, broken-audit rendering |
| Public API | `__all__` exports, version/author, result types |

## Determinism

- The router, redactor, policy engine, and agents are pure functions of the case
  plus configuration.
- The audit ledger accepts an injectable clock. Tests use a fixed timestamp to
  assert stable entries; default runs use UTC.
- Message IDs are derived from case ID and sequence.
- No test sleeps, makes a network call, or depends on external services.
- No randomness is used.

## Legacy `test/` directory

The original repository contains seven legacy test files targeting the earlier
CrewAI/LangChain application and external services:

```text
test/test_apps.py
test/test_image2audio.py
test/test_image2text.py
test/test_image2video.py
test/test_metrics.py
test/test_performance.py
test/test_prompts.py
```

In this checkout those files are **empty placeholders**, so they neither pass nor
fail; they are preserved as part of the archive. They are excluded from the default
run via:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-config --strict-markers --ignore=test"
```

**No claim is made that the legacy tests pass.** If they are restored with content,
they should be run explicitly against their original environment, and their
dependencies/services must be documented separately.

Similarly, `src/` and `config/` are preserved placeholders for the original app;
they are not imported or exercised by the governance tests. The notebooks are
research artifacts and are not executed in CI.

## CI

`.github/workflows/ci.yml` runs on push and pull request with a matrix of Python
**3.10, 3.11, and 3.12**:

1. install `pytest` and `pytest-cov`,
2. run `python -m pytest -q`,
3. run the coverage command with the 100% gate from `pyproject.toml`,
4. smoke-test `python -m ieesbots --help` and `--demo`.

The workflow is configured but has not been executed in this local session. Only
Python 3.12.8 was available locally, so no claim is made that 3.10/3.11 were run
here. The matrix exists to verify compatibility on CI.

## Known gaps in verification

- **No clinical validation.** Rules are illustrative tables and keyword matches.
- **No performance/load testing.** The package is synchronous and in-memory.
- **No fuzzing/property testing.** JSON validation and regexes are tested by
  example, not exhaustively.
- **No adversarial redaction testing.** Names, addresses, and contextual
  identifiers are not handled.
- **No fairness/bias evaluation.** Symptom keywords may perform differently across
  populations and presentations.
- **No concurrency testing.** Audit integrity is single-process.
- **No browser/UI testing.** There is no UI.
- **No real CrewAI/Ollama integration test.** Live adapters are explicitly out of
  the tested core.
- **Coverage ≠ correctness.** 100% branch coverage of a small deterministic
  package says the code paths run; it says nothing about clinical validity.

## Adding tests

- Put tests in `tests/` and import the public API from `ieesbots`.
- Cover both outcomes of every new condition; the CI gate requires 100% branch
  coverage of the package.
- Use synthetic values only. Never add real patient data, names, MRNs, or
  credentials.
- For timing, inject a clock instead of sleeping.
- For CLI tests, use `capsys`; for file input, use `tmp_path`.
- For audit tamper tests, mutate a copy with `object.__setattr__` or
  `dataclasses.replace` and assert the specific failure reason.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full checklist.
