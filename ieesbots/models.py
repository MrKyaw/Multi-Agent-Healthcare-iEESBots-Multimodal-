"""Typed domain models for the iEESBots governance core.

Every object in this module is a plain :mod:`dataclasses` value object.  The
module deliberately has no third-party or network dependencies so that the
orchestration logic can be exercised deterministically on a laptop or in CI.

All patient data used with these models is **synthetic**.  This package is a
research prototype, not a medical device.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .exceptions import CaseValidationError


class AgentRole(str, Enum):
    """The five roles in the synthetic care-navigation workflow."""

    TRIAGE = "triage"
    EVIDENCE = "evidence"
    MEDICATION = "medication"
    HUMAN_REVIEW = "human_review"
    SUMMARIZER = "summarizer"

    @property
    def label(self) -> str:
        """Human-readable role name used in reports and CLI output."""

        return self.value.replace("_", " ").title()


class ConsentScope(str, Enum):
    """Least-privilege consent scopes granted per agent role."""

    CARE_TRIAGE = "care.triage"
    EVIDENCE_RETRIEVAL = "evidence.retrieve"
    MEDICATION_REVIEW = "medication.review"
    HUMAN_REVIEW = "human.review"
    SUMMARY_GENERATION = "summary.generate"


class Severity(str, Enum):
    """Ordered-ish severity labels for policy findings."""

    INFO = "info"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class Verdict(str, Enum):
    """Outcome of the safety policy engine.

    ``ALLOW`` permits an automated draft, ``ESCALATE`` requires a licensed
    human reviewer, and ``BLOCK`` stops the workflow from producing clinical
    guidance at all.
    """

    ALLOW = "allow"
    ESCALATE = "escalate"
    BLOCK = "block"


class RunStatus(str, Enum):
    """Terminal status of one orchestrated case."""

    COMPLETED = "completed"
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"
    BLOCKED_CONSENT = "blocked_consent"
    BLOCKED_SAFETY = "blocked_safety"


@dataclass(frozen=True)
class CaseFlags:
    """Structured, machine-readable hints supplied alongside a case.

    Flags are intentionally explicit rather than inferred from free text so
    that routing is reproducible and auditable.
    """

    chest_pain: bool = False
    polypharmacy: bool = False
    imaging_available: bool = False
    mental_health_crisis: bool = False
    pregnancy: bool = False
    pediatric: bool = False


@dataclass(frozen=True)
class EvidenceItem:
    """A synthetic evidence snippet with provenance metadata."""

    evidence_id: str
    title: str
    source: str
    text: str
    kind: str = "guideline"

    def searchable_text(self) -> str:
        """Return the lower-cased text used by the deterministic retriever."""

        return f"{self.title} {self.text}".lower()


@dataclass(frozen=True)
class PatientCase:
    """A fully synthetic care-navigation case.

    The model contains no identifiers beyond what the caller supplies.  The
    orchestrator redacts the free-text ``narrative`` before any agent sees it
    and keeps the reversible token vault in memory only.
    """

    case_id: str
    narrative: str
    age: int
    symptoms: tuple[str, ...] = ()
    medications: tuple[str, ...] = ()
    allergies: tuple[str, ...] = ()
    evidence: tuple[EvidenceItem, ...] = ()
    flags: CaseFlags = field(default_factory=CaseFlags)
    consent_scopes: frozenset[ConsentScope] = frozenset()

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise CaseValidationError("case_id must be a non-empty string")
        if not 0 <= self.age <= 130:
            raise CaseValidationError(
                f"age must be between 0 and 130, received {self.age!r}"
            )


@dataclass(frozen=True)
class RoutingDecision:
    """One agent selection with its precedence and plain-language rationale."""

    role: AgentRole
    priority: int
    rationale: str
    required_scope: ConsentScope


@dataclass(frozen=True)
class RoutingPlan:
    """Ordered set of agents selected for a case."""

    decisions: tuple[RoutingDecision, ...]

    @property
    def roles(self) -> tuple[AgentRole, ...]:
        """Roles in execution order."""

        return tuple(decision.role for decision in self.decisions)

    @property
    def scopes(self) -> tuple[ConsentScope, ...]:
        """Scopes required by the selected agents, in execution order."""

        return tuple(decision.required_scope for decision in self.decisions)


@dataclass(frozen=True)
class ConsentDecision:
    """Authorization result for a single agent."""

    role: AgentRole
    scope: ConsentScope
    granted: bool
    reason: str


@dataclass(frozen=True)
class PolicyFinding:
    """A single clinical-safety finding produced by a deterministic rule."""

    rule_id: str
    category: str
    severity: Severity
    verdict: Verdict
    rationale: str
    requires_human: bool = True


@dataclass(frozen=True)
class PolicyAssessment:
    """Aggregate policy result with explicit block/escalation precedence."""

    findings: tuple[PolicyFinding, ...]
    verdict: Verdict
    requires_human: bool

    @property
    def blocked_reasons(self) -> tuple[str, ...]:
        """Rule identifiers that caused a hard block."""

        return tuple(
            finding.rule_id
            for finding in self.findings
            if finding.verdict is Verdict.BLOCK
        )

    @property
    def escalation_reasons(self) -> tuple[str, ...]:
        """Rule identifiers that require human review."""

        return tuple(
            finding.rule_id
            for finding in self.findings
            if finding.verdict is Verdict.ESCALATE
        )


@dataclass(frozen=True)
class Citation:
    """A citation to synthetic evidence or to a policy rule."""

    identifier: str
    title: str
    source: str
    kind: str


@dataclass(frozen=True)
class SummarySection:
    """One heading/body pair in the structured summary."""

    heading: str
    body: str


@dataclass(frozen=True)
class Summary:
    """Structured, cited output returned to the caller."""

    title: str
    status: str
    sections: tuple[SummarySection, ...]
    citations: tuple[Citation, ...]
    disclaimers: tuple[str, ...]

    def render(self) -> str:
        """Render the summary as Markdown for humans and the CLI."""

        lines = [f"# {self.title}", "", f"**Status:** {self.status}", ""]
        for section in self.sections:
            lines.extend([f"## {section.heading}", "", section.body, ""])
        lines.extend(["## Citations", ""])
        for citation in self.citations:
            lines.append(
                f"- [{citation.identifier}] {citation.title} — {citation.source}"
            )
        lines.extend(["", "## Disclaimers", ""])
        for disclaimer in self.disclaimers:
            lines.append(f"- {disclaimer}")
        return "\n".join(lines).rstrip() + "\n"

    def to_dict(self) -> dict[str, Any]:
        """Serialize the summary for JSON output."""

        return {
            "title": self.title,
            "status": self.status,
            "sections": [
                {"heading": section.heading, "body": section.body}
                for section in self.sections
            ],
            "citations": [
                {
                    "identifier": citation.identifier,
                    "title": citation.title,
                    "source": citation.source,
                    "kind": citation.kind,
                }
                for citation in self.citations
            ],
            "disclaimers": list(self.disclaimers),
        }


@dataclass(frozen=True)
class AuditEntry:
    """Immutable entry in the hash-chained audit ledger."""

    index: int
    timestamp: str
    actor: str
    action: str
    details: Mapping[str, Any]
    prev_hash: str
    entry_hash: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entry, including its chain hashes."""

        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "action": self.action,
            "details": dict(self.details),
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
        }


@dataclass(frozen=True)
class AuditVerification:
    """Result of recomputing and validating the full audit chain."""

    valid: bool
    broken_index: int | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize the verification result."""

        return {
            "valid": self.valid,
            "broken_index": self.broken_index,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RedactionReport:
    """Counts of PHI categories removed from a piece of text."""

    counts: Mapping[str, int]
    total: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize redaction counts for reports and audit entries."""

        return {"counts": dict(self.counts), "total": self.total}


@dataclass(frozen=True)
class RunResult:
    """Complete, serializable result of one orchestrated synthetic case."""

    case_id: str
    status: RunStatus
    redacted_narrative: str
    plan: RoutingPlan
    consent: tuple[ConsentDecision, ...]
    policy: PolicyAssessment
    redaction: RedactionReport
    messages: tuple[Any, ...]
    summary: Summary
    ledger: tuple[AuditEntry, ...]
    audit: AuditVerification
    requires_human: bool

    def to_dict(self) -> dict[str, Any]:
        """Serialize the full run for ``--json`` output.

        Only redacted text and token counts are included; the reversible vault
        never leaves the process.
        """

        return {
            "case_id": self.case_id,
            "status": self.status.value,
            "requires_human": self.requires_human,
            "redacted_narrative": self.redacted_narrative,
            "redaction": self.redaction.to_dict(),
            "routing": [
                {
                    "role": decision.role.value,
                    "priority": decision.priority,
                    "rationale": decision.rationale,
                    "required_scope": decision.required_scope.value,
                }
                for decision in self.plan.decisions
            ],
            "consent": [
                {
                    "role": decision.role.value,
                    "scope": decision.scope.value,
                    "granted": decision.granted,
                    "reason": decision.reason,
                }
                for decision in self.consent
            ],
            "policy": {
                "verdict": self.policy.verdict.value,
                "requires_human": self.policy.requires_human,
                "findings": [
                    {
                        "rule_id": finding.rule_id,
                        "category": finding.category,
                        "severity": finding.severity.value,
                        "verdict": finding.verdict.value,
                        "rationale": finding.rationale,
                        "requires_human": finding.requires_human,
                    }
                    for finding in self.policy.findings
                ],
            },
            "messages": [message.to_dict() for message in self.messages],
            "summary": self.summary.to_dict(),
            "audit": {
                "verification": self.audit.to_dict(),
                "entries": [entry.to_dict() for entry in self.ledger],
            },
        }
