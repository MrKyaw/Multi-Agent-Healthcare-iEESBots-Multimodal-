# Contributing

Thanks for taking a look. This is a synthetic research prototype and a portfolio
project, not a clinical product. Contributions that improve clarity, test rigor, or
governance mechanics are welcome; contributions that imply clinical validity or add
real patient data are not.

> **Do not contribute real patient data, PHI, credentials, proprietary guidelines,
> or anything that could identify a person.** All examples and tests must be
> fictional.

## Ground rules

1. **Preserve the archive.** Do not delete or rewrite the notebooks, PDFs, images,
   configuration, legacy tests, or `LICENSE`. Additive changes are preferred.
2. **No clinical claims.** Do not add accuracy, safety, or outcome metrics that were
   not measured. Do not describe the project as a medical device or validated tool.
3. **Keep the core offline.** `ieesbots/` must use the Python standard library only.
   No network calls, model providers, databases, or background threads.
4. **Keep it deterministic.** Same case + fixed clock → same route, findings, tokens,
   and audit hashes. No randomness, sleeps, or wall-clock dependencies in logic.
5. **Maintain 100% coverage.** Every new line and branch in `ieesbots/` needs a test.
6. **Do not bypass controls.** New features must preserve the order: redact → route
   → consent → policy → agents → human gate → summary → audit verify.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

python -m pytest -q
python -m pytest --cov=ieesbots --cov-branch --cov-report=term-missing
python -m ieesbots --demo
```

Python 3.10+ is required. CI targets 3.10, 3.11, and 3.12.

## What to work on

Good first contributions:

- clarify documentation or diagrams without changing behavior,
- add a synthetic case under `examples/` that exercises a documented path,
- improve error messages while keeping tests and coverage intact,
- add a policy rule **with** tests and a docs update,
- strengthen a test that currently checks only one side of a branch,
- improve accessibility/readability of CLI output.

Please open an issue first for larger changes, especially anything that alters the
control order, policy precedence, or public contracts.

## Adding a policy rule

1. Choose a stable rule ID (e.g., `GER-001`) and category.
2. Implement it in `ieesbots/policy.py` (or a primitive in `clinical_rules.py`).
3. Decide severity and verdict deliberately. Default to `ESCALATE` when uncertain;
   reserve `BLOCK` for direct, high-confidence contraindications.
4. Ensure every finding sets `requires_human=True` unless there is a documented,
   reviewed reason not to.
5. Add tests for:
   - the rule firing,
   - the rule not firing,
   - precedence interaction with `BLOCK`/`ESCALATE`/`ALLOW`,
   - the rendered summary and citation ID.
6. Update the rule table in `ARCHITECTURE.md` and, if relevant,
   `docs/SAFETY_AND_ETHICS.md`.
7. Run the coverage gate.

Do not phrase rules as clinical guidance. Use "synthetic rule" language and cite
the deterministic policy engine, not medical literature you have not validated.

## Adding a PHI pattern

1. Add a `PHIKind` if a new category is needed.
2. Add the compiled pattern to `DEFAULT_PATTERNS` in the correct order (specific
   before generic).
3. Add positive tests and **false-positive tests** (text that should not change).
4. Verify stable tokens for repeated values and round-trip `detokenize`.
5. Update the redaction table in `ARCHITECTURE.md`.
6. Remember: regex redaction is not de-identification. Do not claim compliance.

## Adding an agent

1. Define a frozen payload dataclass in `contracts.py` and add a `MessageKind`.
2. Implement a deterministic agent in `agents.py`.
3. Add routing rules and rationale in `router.py` if the agent is conditional.
4. Add consent scope mapping in `consent.py` if it processes data.
5. Record a typed message and audit event in `orchestrator.py`.
6. Summarize its output with citations or explicitly state it was not routed.
7. Cover present/absent paths, success/denial paths, and serialization.

## Style

- Python 3.10+, `from __future__ import annotations`.
- Type hints on public functions and dataclasses.
- Docstrings explain *why* and state limitations.
- Frozen dataclasses for domain values; no mutable global state.
- Custom exceptions for package-level failures.
- Keep modules focused; prefer small pure functions.
- No new runtime dependencies without prior discussion.
- Comments should add information, not restate code.

No formatter/linter is enforced in CI. If you use one, keep the diff focused.

## Tests

- All tests live in `tests/`.
- Use `pytest`, `capsys`, `tmp_path`, and `monkeypatch`.
- Use synthetic identifiers only.
- Inject the audit clock; do not sleep.
- Assert on specific rule IDs, reasons, and statuses rather than loose strings.
- The coverage gate is `fail_under = 100` with `branch = true`, scoped to
  `ieesbots`.
- Legacy `test/` is excluded; do not claim it passes.

Run before opening a pull request:

```bash
python -m pytest -q
python -m pytest --cov=ieesbots --cov-branch --cov-report=term-missing
python -m ieesbots --demo > /dev/null
```

## Documentation

- Update `README.md` for user-visible changes.
- Update `ARCHITECTURE.md` for control flow, routing, rules, or contracts.
- Update `docs/DESIGN_DECISIONS.md` for significant trade-offs.
- Update `docs/SAFETY_AND_ETHICS.md` for new risks or limitations.
- Update `TESTING.md` for test strategy, coverage, or exclusions.
- Report only measured results; never fabricate metrics.

## Pull requests

Include:

- what changed and why,
- the exact test and coverage commands you ran,
- the observed summary (test count and coverage),
- any new residual risks or limitations,
- confirmation that no real data or secrets were added.

Please do not include generated coverage artifacts (`htmlcov/`, `.coverage`) or
virtual environments in a PR. See `.gitignore`.

## Code of conduct

Be respectful, specific, and honest about uncertainty. Critique code and claims, not
people. Given the healthcare context, prioritize patient safety and privacy over
demo impact.

## License

By contributing, you agree that your contributions are licensed under the
repository's [MIT License](LICENSE).
