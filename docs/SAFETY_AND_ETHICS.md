# Safety and Ethics

> **This repository is a synthetic research prototype. It is not a medical device.**
> It does not diagnose, treat, prescribe, triage real patients, or provide medical
> advice. It has not been clinically validated, reviewed by regulators, or tested
> with real patient data. Do not use it in clinical care, emergency response, or any
> decision affecting a person's health.

The goal of this document is to state plainly what the prototype does, what it
cannot do, and which risks remain after its controls.

---

## 1. Intended use

The package is intended for:

- demonstrating governance patterns for multi-agent systems,
- teaching and reviewing deterministic safety controls,
- testing software engineering practices (typed contracts, coverage, audit),
- serving as a discussion artifact for AI safety and clinical informatics.

## 2. Prohibited and unsupported uses

It is **not** intended or safe for:

- diagnosis, triage, treatment, or medication selection for any person,
- patient-facing chat or advice,
- emergency or urgent-care decision-making,
- claims of HIPAA, GDPR, FDA, MDR, or NHS compliance,
- processing real protected health information (PHI),
- autonomous action on messages, prescriptions, or referrals,
- surveillance, scoring, or profiling of individuals,
- replacing a clinician, pharmacist, or emergency service.

If you need urgent medical help, contact local emergency services. This software
cannot help you.

---

## 3. Synthetic data only

- The demo case (`SYN-1001`) is fictional.
- Identifiers such as `MRN: 8891234`, `(555) 010-2030`, and
  `jane.synthetic@example.test` are invented.
- Evidence items are labeled "fictional fixture (not a guideline)".
- No dataset, model weights, or real patient records are included.
- The core performs no network I/O. The only file read is a `--case` path supplied
  explicitly by the user.
- Tests use temporary files (`tmp_path`) and fixed clocks; they do not touch
  external services.

**Do not contribute real patient data, credentials, or proprietary clinical
content.** See [CONTRIBUTING.md](../CONTRIBUTING.md).

---

## 4. Threat model and controls

The controls are educational, not certified. Residual risk is listed honestly.

| Risk | Example scenario | Implemented control | Residual risk |
|---|---|---|---|
| Unauthorized processing | Agent summarizes a case without consent | Consent gate runs before policy/agents; denial returns `BLOCKED_CONSENT` and an audit reason | Consent records are caller-supplied booleans/scopes; no identity proof, expiry, revocation, or guardian consent flow |
| PHI leakage | MRN/email appears in summary or JSON | Ordered regex redaction; only tokens/counts emitted; vault stays in memory | Names, addresses, ages, rare conditions, and contextual identifiers are not detected; regex can over/under-match |
| Unsafe medication advice | Penicillin allergy + amoxicillin | `ALG-001` hard `BLOCK`; no medication recommendation; human required | Tiny family table; misspelled drugs, metabolites, cross-reactivity, and dosing interactions are out of scope |
| Missed emergency | Chest pain summarized as routine | Red-flag rules force `ESCALATE`; triage acuity critical; human packet | Keyword matching misses atypical phrasing and non-text presentations; no vitals, ECG, or clinician exam |
| Missing grounding | Confident summary with no evidence | `EVD-001` escalation when a red flag has no evidence | Evidence is fictional; retrieval is keyword overlap, not semantic or validated |
| Automation bias | Caller treats the draft as final | Explicit `AWAITING_HUMAN_REVIEW`, "not final" language, disclaimers, mandatory human flag | A determined caller can ignore status fields; no UI enforcement or reviewer sign-off |
| Audit tampering | Edit an entry or remove an event | SHA-256 chain detects content/index/prev-hash changes | In-memory only; whole-ledger deletion, truncation, and timestamp forgery are not prevented; no signatures or external anchoring |
| Non-reproducibility | Different route on retry | Pure router, deterministic rules, fixed priority, injectable clock | Python/library version changes and caller-supplied flags can change behavior |
| Silent agent failure | Agent omitted from output | Typed messages and audit events per invocation; summary notes absent optional agents | No runtime monitoring, retries, circuit breakers, or alerting |
| Prompt injection via evidence | Malicious text manipulates an LLM | No LLM in core; evidence is treated as data | A future live adapter could reintroduce this risk; it must sanitize and isolate prompts |
| Data exfiltration | Agent calls an external API | No network code; zero runtime dependencies | Python itself and user-supplied case files are trusted; adapters could add egress |

### Redaction is not de-identification

The regexes cover five categories (email, labeled MRN, SSN, phone, date). They do
not cover:

- names, addresses, postal codes, URLs, IP addresses,
- device IDs, account numbers, insurance IDs, license plates,
- faces, voices, images, or metadata,
- combinations that re-identify a person,
- identifiers split across lines or obfuscated.

Do not treat the redaction report as proof of anonymity. For real de-identification,
use a validated process with legal and privacy review.

### Audit chain is not immutable storage

The chain detects edits within the in-memory list. It does not prevent:

- deleting the whole ledger,
- truncating the final entries,
- forging timestamps,
- rewriting all hashes from genesis,
- concurrent writers or rollback attacks.

Production audit requires append-only storage, access control, trusted time, and
ideally signatures or external anchoring.

---

## 5. Clinical and scientific limitations

- **No clinical validation.** Rules were not derived from guidelines, reviewed by
  clinicians, or tested against outcomes.
- **No diagnostic performance.** There is no sensitivity, specificity, accuracy, or
  outcome metric. None should be inferred.
- **No patient population.** Pediatric, pregnancy, geriatric, renal, hepatic,
  pharmacogenomic, and multimorbidity logic is absent beyond coarse flags.
- **No real evidence retrieval.** `EvidenceAgent` performs keyword overlap over
  caller-supplied fictional snippets.
- **No medication database.** `ALLERGY_FAMILIES` is a tiny illustrative table.
- **No vitals, labs, images, or signals.** The multimodal research is preserved in
  notebooks but is not part of the governed core.
- **No clinician usability testing.** The summary format has not been evaluated.
- **No fairness evaluation.** Keyword lists can under-trigger atypical
  presentations and over-trigger others; language and cultural variation are not
  handled.
- **No uncertainty calibration.** Verdicts are deterministic rules, not
  probabilities.

---

## 6. Ethical considerations

### Human oversight

Every escalation requires a licensed human reviewer. The prototype produces a draft
with citations and explicit "not final" language. It does not contact a clinician,
verify identity, or record a real sign-off. The human-review packet is a
demonstration artifact.

### Automation bias

Deterministic output can look authoritative. Disclaimers, status fields, and
sections are designed to counter this, but documentation alone cannot prevent
over-trust. Any real deployment would need workflow controls, training, and
measurable review behavior.

### Equity and access

Keyword rules encode assumptions about how symptoms are described. People who use
different language, are non-native speakers, or present atypically may be
under-served. No demographic evaluation has been performed. A real system would
require intersectional validation and monitoring.

### Privacy and consent

The demo treats consent as explicit scopes supplied with the case. It does not
implement identity verification, capacity assessment, guardian consent, revocation,
or purpose limitation. Real consent is contextual, revocable, and jurisdiction-
specific; this prototype is none of those things.

### Transparency

The repository documents rules, precedence, limitations, and failure modes. Source
code and tests are open for review. However, a rule table is not an explanation of
a clinical decision, and citations to fictional evidence have no clinical authority.

### Dual use

Governance tooling can be repurposed to create a false impression of safety. Do not
cite this repository as evidence that a clinical AI system is safe, compliant, or
validated. Coverage metrics describe code paths, not patient outcomes.

---

## 7. Regulatory and compliance status

**None.**

- Not a medical device under FDA, EU MDR, or any other regime.
- Not HIPAA compliant: no BAAs, access control, encryption at rest, retention, or
  audit infrastructure.
- Not GDPR compliant: no lawful basis, DPA, data-subject rights, or transfer
  safeguards.
- Not validated under any clinical quality standard (e.g., IEC 62304, ISO 14971,
  ISO 13485).
- No CE mark, FDA clearance, or clinical evaluation.

Any use with real data or real care would require legal, privacy, security,
clinical, and regulatory work far beyond this repository.

---

## 8. Safe experimentation checklist

If you explore or extend this prototype:

- [ ] Use only synthetic or fully de-identified data you are authorized to use.
- [ ] Keep it offline; do not add network calls to the tested core.
- [ ] Do not present output to patients or use it to make care decisions.
- [ ] Keep disclaimers in every generated summary.
- [ ] Preserve the control order: redact → route → consent → policy → agents →
      human gate → summary → audit verify.
- [ ] Add tests for both outcomes of every new branch; keep the 100% gate.
- [ ] Treat new rules as hypotheses, not clinical guidance.
- [ ] Document residual risk and avoid compliance claims.
- [ ] If adding a live LLM adapter, isolate prompts, sanitize evidence, log calls,
      and never let the model bypass consent or policy.
- [ ] If real PHI is ever involved, stop and consult privacy/security/legal experts.

---

## 9. Reporting concerns

If you find a safety, privacy, or security issue in this prototype, please open a
GitHub issue with a synthetic reproduction. Do **not** include real patient data,
credentials, or exploit details that could harm a deployed system. This is a
portfolio/research project with no production deployment or incident-response
guarantee.

---

## 10. Summary

The prototype demonstrates **governance mechanics**: explicit consent, redaction,
policy precedence, human escalation, and tamper-evident audit. It does **not**
demonstrate clinical safety or effectiveness. Those are different problems, and
the second cannot be established by unit tests or a demo case.

**Synthetic research prototype. Not a medical device. Not for clinical use.**
