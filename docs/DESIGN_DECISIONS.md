# Design Decisions

> Synthetic research prototype. Not a medical device or clinical decision-support
> system. These records explain engineering choices, not clinical claims.

Format: context → decision → consequences. Decisions are intentionally small and
reversible where practical.

---

## ADR-001: Keep the tested orchestration core deterministic and LLM-free

**Context.** The original project demonstrated multimodal agents backed by CrewAI,
Groq, Ollama, and Replicate. LLM outputs are non-deterministic, require network and
keys, and are difficult to use as a safety boundary. A reviewer cannot tell whether
a passing test means the governance logic works or the model happened to comply.

**Decision.** Implement the governance core as pure Python rules. No network, no
prompts, no model imports in `ieesbots/`. Document live CrewAI/Ollama as an optional
adapter behind the typed contracts.

**Consequences.**
- Reproducible routes, findings, tokens, and audit hashes.
- Tests run offline in under a second.
- The prototype does not demonstrate LLM reasoning quality; that remains in the
  preserved notebooks.
- A future adapter must not be allowed to bypass consent, policy, or audit.

**Alternatives considered.** Mocking LLM calls (still couples tests to prompt
shape); recorded fixtures (brittle and opaque); no governance core (not credible).

---

## ADR-002: Enforce a fixed control order and fail closed

**Context.** A common failure in agent systems is that logging, summarization, or
tool calls happen before authorization. Ordering must be explicit and testable.

**Decision.** `Orchestrator.run` performs exactly:

1. redact PHI,
2. route,
3. authorize consent,
4. evaluate policy,
5. run routed agents,
6. build human-review packet when required,
7. summarize,
8. verify audit chain.

Missing consent returns `BLOCKED_CONSENT`; a `BLOCK` verdict returns
`BLOCKED_SAFETY`; neither path invokes an agent or produces clinical guidance.

**Consequences.**
- A denial is observable in output and audit, not an exception that may be caught
  and ignored.
- Blocked paths still return a cited, disclaimed refusal summary.
- More code and tests than a single happy path; worthwhile for reviewability.

**Alternatives considered.** Authorize per tool call (allows partial processing and
harder reasoning about state); exceptions for denial (easy to swallow); policy after
agents (too late to prevent unsafe drafts).

---

## ADR-003: Represent consent as decisions, not exceptions

**Context.** The package defines `ConsentDeniedError`, but the orchestrator needs to
report *which* scopes were missing and still produce a structured result.

**Decision.** `ConsentGate.authorize` returns a frozen `ConsentDecision` with role,
scope, granted flag, and stable reason. The orchestrator aggregates denials, audits
them, and returns `BLOCKED_CONSENT`. The exception type remains available for
callers that prefer fail-fast behavior in other contexts.

**Consequences.**
- Multiple denied scopes can be reported in one run.
- Audit reasons are uniform (`missing required scope '<scope>'`).
- Callers must check `granted`; the type system cannot enforce it.

**Alternatives considered.** Raising on first denial (loses information); boolean
return (loses scope and reason).

---

## ADR-004: Route with explicit numeric precedence and rationale

**Context.** LLM routers are hard to audit and can vary between runs. Healthcare
workflows need an explainable selection of evidence, medication, and human review.

**Decision.** `AgentRouter` evaluates documented trigger lists and assigns fixed
priorities: triage 10, evidence 20, medication 30, human review 40, summarizer 90.
All matching agents are included; rationale strings are joined and stored.

**Consequences.**
- Same case → same plan, byte for byte.
- Adding a trigger requires a test and a docs update.
- Rules are coarse; atypical presentations may be misrouted.
- Priority numbers encode sequencing, not clinical importance.

**Alternatives considered.** Mutual exclusivity (would drop needed agents); LLM
routing (non-deterministic); unordered set (unstable output).

---

## ADR-005: Policy precedence `BLOCK > ESCALATE > ALLOW`

**Context.** A case can have benign and dangerous findings at once. Averaging or
last-write-wins is unsafe.

**Decision.** Evaluate all rules; any `BLOCK` wins, otherwise any `ESCALATE`, else
`ALLOW`. Every finding carries a stable rule ID, category, severity, verdict,
rationale, and `requires_human` flag.

**Consequences.**
- An allergy conflict cannot be diluted by a routine triage result.
- Findings remain individually inspectable and citable.
- The policy is conservative and will over-escalate; that is intentional for a
  prototype.

**Alternatives considered.** Weighted risk score (opaque and easy to tune unsafely);
first-match-wins (order-dependent and fragile).

---

## ADR-006: Allergy conflicts produce a hard block

**Context.** Medication guidance is the highest-consequence output in the demo.
False reassurance is worse than no answer.

**Decision.** Normalize allergy and medication names; match by containment or shared
illustrative family. Any match yields `ALG-001`, critical severity, `BLOCK`, and a
human requirement. No medication recommendation is generated on that path.

**Consequences.**
- Safe failure mode and clear audit record.
- Over-inclusive matching causes false blocks (e.g., substring coincidences).
- The family table is tiny and not a drug database.

**Alternatives considered.** Warning only (ignorable); LLM adjudication
(non-deterministic and unsafe); no check (unacceptable).

---

## ADR-007: Redact PHI at the boundary with reversible local tokens

**Context.** Demonstrations often leak identifiers into summaries, logs, or JSON.
At the same time, tests need to prove that redaction is reversible without exposing
originals in output.

**Decision.** Apply ordered regex rules for email, labeled MRN, SSN, phone, and
dates. Replace each unique value with a stable token (`[[MRN_1]]`). Store the
mapping in a process-local `PhiVault`; expose only tokens and counts in results.
`detokenize` reverses known tokens and leaves unknown tokens unchanged.

**Consequences.**
- Round-trip behavior is testable.
- Repeated values keep one token, improving consistency.
- Regex is not de-identification: names, addresses, and contextual identifiers are
  missed; patterns can produce false positives.
- The vault is not encrypted or persisted; it is a test/demo mechanism.

**Alternatives considered.** One-way hashing (cannot demonstrate round trip);
external NLP de-identifier (dependency and network); no redaction (unacceptable).

---

## ADR-008: Hash-chain the audit ledger

**Context.** Audit logs are only useful if tampering is detectable. A plain list of
events can be edited silently.

**Decision.** Each entry commits to index, timestamp, actor, action, canonical JSON
details, and the previous hash. `verify()` recomputes the chain and returns the
first broken link; `verify_or_raise()` raises `AuditIntegrityError`.

**Consequences.**
- Editing details, changing an index, or swapping a hash is detected in tests.
- The chain is in-memory; deleting the whole ledger is not prevented.
- No signatures, timestamps from a trusted authority, or external anchoring.
- Canonical JSON keeps hashes stable across runs with a fixed clock.

**Alternatives considered.** Plain JSONL (no tamper evidence); database triggers
(infrastructure); blockchain (overkill and misleading).

---

## ADR-009: Frozen dataclasses and typed message payloads

**Context.** Dictionary-passing between agents hides schema drift and makes tests
brittle.

**Decision.** Domain values and agent payloads are frozen dataclasses with explicit
types and `to_dict()` serializers. Message envelopes use `MessageKind` and
`AgentRole` enums.

**Consequences.**
- Accidental mutation is rejected.
- Contracts are discoverable and testable.
- Serialization is manual but explicit; no third-party schema library.
- Python 3.10+ required for modern typing syntax (`X | None`).

**Alternatives considered.** Pydantic (dependency); TypedDict (no runtime
validation); plain dicts (unsafe).

---

## ADR-010: Zero runtime dependencies

**Context.** Portfolio reviewers and CI should be able to run the governance core
without installing a fragile ML stack.

**Decision.** Use only the Python standard library in `ieesbots/`. Keep optional
`dev` and `live` extras in `pyproject.toml`; the latter is documentation of a
possible adapter, not an import.

**Consequences.**
- Fast, portable, auditable.
- No built-in JSON Schema validation; hand-written validation is tested.
- No third-party crypto; `hashlib` SHA-256 is sufficient for a demo chain.
- Live model integration requires deliberate extra work.

**Alternatives considered.** Pydantic + jsonschema + cryptography (more capable but
heavier); notebook-only demo (not testable).

---

## ADR-011: Provide a CLI with text, JSON, and exit codes

**Context.** Recruiters and reviewers should be able to see the system work in one
command; automation needs machine-readable output and meaningful failures.

**Decision.** `python -m ieesbots` supports `--demo`, `--case FILE`, `--json`, and
`--help`. Exit codes: `0` completed/awaiting review, `1` blocked, `2` invalid input.

**Consequences.**
- One-command demo and scriptable JSON.
- Exit codes distinguish governance blocks from malformed input.
- Output includes disclaimers and audit status every time.

**Alternatives considered.** Notebook demo only (not automation-friendly); web UI
(adds dependencies and shifts focus away from governance).

---

## ADR-012: Preserve the legacy app and exclude its tests from the default run

**Context.** The repository is also an archive of original coursework and research.
Deleting old code or tests would destroy provenance. The legacy tests target an app
with external services and are not part of the new package.

**Decision.** Keep every original file. Configure pytest with
`testpaths = ["tests"]` and `--ignore=test`. Document the exclusion and make no
claim that legacy tests pass. In this checkout, the legacy test files are empty
placeholders.

**Consequences.**
- Default `pytest` is meaningful and fast.
- The archive remains intact.
- A reviewer might expect old tests to run; `TESTING.md` explains why they do not.
- Coverage is scoped to `ieesbots` only, not notebooks or placeholders.

**Alternatives considered.** Delete legacy tests (violates preservation); run them
(irrelevant failures and missing services); rewrite them (out of scope and would
fabricate coverage).

---

## ADR-013: Use fictional evidence and avoid fabricated metrics

**Context.** Healthcare demos often cite real-sounding studies or invent accuracy
numbers. That is misleading and unsafe.

**Decision.** All evidence items are explicitly labeled fictional fixtures. Every
summary repeats disclaimers. Documentation reports only measured test/coverage
results; no clinical performance metrics are claimed.

**Consequences.**
- The repository is honest about what is and is not validated.
- Citations demonstrate plumbing, not clinical authority.
- Reviewers cannot mistake the demo for evidence-based guidance.

**Alternatives considered.** Real guideline text (licensing and context risk);
invented statistics (unacceptable).

---

## ADR-014: Model human review as a terminal status, not a side effect

**Context.** If a high-risk case is summarized and silently returned, a caller may
treat it as final.

**Decision.** `RunStatus.AWAITING_HUMAN_REVIEW` is explicit when policy requires
review. The summary status says "human review required", a `HumanReviewRequest`
message is produced, and the human-oversight section states the draft is not final.

**Consequences.**
- Callers cannot mistake escalation for completion without ignoring explicit fields.
- The CLI exits `0` for awaiting review (the run succeeded) while displaying the
  pending human step.
- There is no actual reviewer workflow or identity verification; the packet is a
  demonstration artifact.

**Alternatives considered.** Reuse `COMPLETED` with a boolean (easy to ignore);
raise an exception (loses the cited draft and audit context).
