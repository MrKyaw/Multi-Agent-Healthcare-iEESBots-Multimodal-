# About iEESBots Governance Core

**One line:** A deterministic, offline governance layer for a synthetic
multi-agent healthcare prototype — consent, PHI redaction, safety policy,
human-in-the-loop review, and a hash-chained audit trail, with 100% line and
branch coverage.

**Author:** Kyaw Kyaw Oo · [kyaw.tech@gmail.com](mailto:kyaw.tech@gmail.com) ·
[github.com/MrKyaw](https://github.com/MrKyaw)

> Research prototype only. Not a medical device. Not for clinical use. All cases
> and identifiers are synthetic.

---

## Tags

`#multi-agent-systems` `#ai-governance` `#ai-safety` `#healthcare-ai`
`#clinical-informatics` `#phi-redaction` `#consent-management`
`#human-in-the-loop` `#audit-trail` `#tamper-evident` `#policy-engine`
`#deterministic-orchestration` `#python` `#dataclasses` `#pytest`
`#branch-coverage` `#standard-library` `#offline` `#crewai` `#llm`
`#multimodal` `#software-engineering` `#portfolio-project`

## Keywords

multi-agent orchestration, AI governance, AI safety engineering, healthcare
chatbot, care navigation, PHI de-identification, reversible tokenization,
least-privilege consent, safety policy engine, red-flag escalation, allergy
conflict detection, polypharmacy, missing evidence, human oversight, audit
ledger, SHA-256 hash chain, deterministic router, typed message contracts,
test coverage, continuous integration, Python 3.10+, no runtime dependencies.

## What is inside

| Area | Summary |
|---|---|
| Original research | Preserved notebooks, PDF, images, CrewAI/LangChain experiments |
| New core | `ieesbots/` — 15 standard-library modules |
| Governance | Consent gate, PHI redactor, policy engine, human review gate |
| Audit | Hash-chained ledger with tamper detection |
| Interface | `python -m ieesbots` with `--demo`, `--json`, `--case` |
| Verification | 133 tests, 100% line + branch coverage, Python 3.10–3.12 CI |

## What it is not

- Not a medical device or clinical decision-support system.
- Not validated against patients, clinicians, or clinical guidelines.
- Not HIPAA/GDPR/FDA/MDR compliant.
- Not a complete de-identification tool.
- Not a distributed or immutable ledger.
- Not an LLM application in its tested core — live CrewAI/Ollama is optional.

## Why it exists

The original project demonstrated multimodal multi-agent routing. This upgrade
adds the engineering discipline that a healthcare-adjacent prototype needs before
anyone can evaluate it responsibly: explicit contracts, deterministic behavior,
enforced authorization, safety verdicts, human escalation, and evidence that the
controls actually work.

## License

MIT. See [LICENSE](LICENSE).
