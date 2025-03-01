"""End-to-end orchestration for one synthetic case.

The orchestrator enforces a fixed governance order:

1. redact PHI from the narrative,
2. route agents deterministically,
3. verify consent scopes before any agent runs,
4. evaluate the safety policy,
5. run only the routed agents,
6. gate finalization on human review,
7. produce a cited draft summary,
8. verify the audit chain.

It never calls a network, model provider, or file outside an explicitly supplied
case path.  The whole run is synchronous and deterministic given a fixed clock.
"""

from __future__ import annotations

from typing import Callable, Optional

from .agents import (
    DISCLAIMERS,
    EvidenceAgent,
    HumanReviewAgent,
    MedicationAgent,
    SummarizerAgent,
    TriageAgent,
)
from .audit import AuditLedger
from .consent import ConsentGate
from .contracts import (
    AgentMessage,
    EvidenceBundle,
    HumanReviewRequest,
    MedicationReview,
    MessageKind,
    SummaryReady,
)
from .models import (
    AgentRole,
    Citation,
    ConsentDecision,
    PatientCase,
    PolicyAssessment,
    RunResult,
    RunStatus,
    RoutingPlan,
    Summary,
    SummarySection,
    Verdict,
)
from .policy import SafetyPolicyEngine
from .redaction import RedactionResult, Redactor
from .router import AgentRouter


class Orchestrator:
    """Coordinate routing, governance, agents, summary, and audit."""

    def __init__(
        self,
        router: AgentRouter | None = None,
        consent_gate: ConsentGate | None = None,
        policy: SafetyPolicyEngine | None = None,
        redactor: Redactor | None = None,
        clock: Optional[Callable[[], str]] = None,
    ) -> None:
        self._router = router if router is not None else AgentRouter()
        self._consent_gate = consent_gate if consent_gate is not None else ConsentGate()
        self._policy = policy if policy is not None else SafetyPolicyEngine()
        self._redactor = redactor if redactor is not None else Redactor()
        self._clock = clock
        self._triage = TriageAgent()
        self._evidence = EvidenceAgent()
        self._medication = MedicationAgent()
        self._human = HumanReviewAgent()
        self._summarizer = SummarizerAgent()

    def run(self, case: PatientCase) -> RunResult:
        """Run one case and return a fully auditable result."""

        redaction = self._redactor.redact(case.narrative)
        ledger = (
            AuditLedger(clock=self._clock)
            if self._clock is not None
            else AuditLedger()
        )
        ledger.append(
            "orchestrator",
            "case.received",
            {
                "case_id": case.case_id,
                "age": case.age,
                "phi_tokens": redaction.report.total,
                "phi_counts": dict(redaction.report.counts),
            },
        )

        plan = self._router.route(case)
        ledger.append(
            "router",
            "plan.created",
            {
                "roles": [role.value for role in plan.roles],
                "priorities": [decision.priority for decision in plan.decisions],
            },
        )

        consent = self._consent_gate.authorize_plan(plan, case.consent_scopes)
        denied = ConsentGate.denied(consent)
        if denied:
            ledger.append(
                "consent_gate",
                "consent.denied",
                {
                    "roles": [decision.role.value for decision in denied],
                    "reasons": [decision.reason for decision in denied],
                },
            )
            summary = self._consent_refusal(case, redaction, plan, consent, denied)
            return RunResult(
                case_id=case.case_id,
                status=RunStatus.BLOCKED_CONSENT,
                redacted_narrative=redaction.text,
                plan=plan,
                consent=consent,
                policy=self._empty_policy(),
                redaction=redaction.report,
                messages=(),
                summary=summary,
                ledger=ledger.entries,
                audit=ledger.verify(),
                requires_human=True,
            )

        ledger.append(
            "consent_gate",
            "consent.granted",
            {"scopes": [decision.scope.value for decision in consent]},
        )

        assessment = self._policy.evaluate(case)
        ledger.append(
            "policy_engine",
            "policy.evaluated",
            {
                "verdict": assessment.verdict.value,
                "requires_human": assessment.requires_human,
                "rules": [finding.rule_id for finding in assessment.findings],
            },
        )

        if assessment.verdict is Verdict.BLOCK:
            ledger.append(
                "policy_engine",
                "safety.blocked",
                {"rules": list(assessment.blocked_reasons)},
            )
            summary = self._safety_refusal(case, redaction, assessment)
            return RunResult(
                case_id=case.case_id,
                status=RunStatus.BLOCKED_SAFETY,
                redacted_narrative=redaction.text,
                plan=plan,
                consent=consent,
                policy=assessment,
                redaction=redaction.report,
                messages=(),
                summary=summary,
                ledger=ledger.entries,
                audit=ledger.verify(),
                requires_human=True,
            )

        messages: list[AgentMessage] = []
        triage = self._triage.assess(case)
        self._record(
            messages,
            ledger,
            case,
            AgentRole.TRIAGE,
            AgentRole.SUMMARIZER,
            MessageKind.TRIAGE_REPORT,
            triage,
            {"acuity": triage.acuity, "red_flags": list(triage.red_flags)},
        )

        evidence: Optional[EvidenceBundle] = None
        if AgentRole.EVIDENCE in plan.roles:
            evidence = self._evidence.retrieve(case)
            self._record(
                messages,
                ledger,
                case,
                AgentRole.EVIDENCE,
                AgentRole.TRIAGE,
                MessageKind.EVIDENCE_BUNDLE,
                evidence,
                {
                    "coverage": evidence.coverage,
                    "matched_ids": list(evidence.matched_ids),
                },
            )

        medication: Optional[MedicationReview] = None
        if AgentRole.MEDICATION in plan.roles:
            medication = self._medication.review(case)
            self._record(
                messages,
                ledger,
                case,
                AgentRole.MEDICATION,
                AgentRole.SUMMARIZER,
                MessageKind.MEDICATION_REVIEW,
                medication,
                {
                    "conflicts": list(medication.conflicts),
                    "polypharmacy": medication.polypharmacy,
                },
            )

        human_request: Optional[HumanReviewRequest] = None
        if AgentRole.HUMAN_REVIEW in plan.roles:
            human_request = self._human.request(case, assessment)
            self._record(
                messages,
                ledger,
                case,
                AgentRole.HUMAN_REVIEW,
                AgentRole.SUMMARIZER,
                MessageKind.HUMAN_REVIEW_REQUEST,
                human_request,
                {"required": True},
            )

        summary = self._summarizer.summarize(
            case=case,
            redaction=redaction,
            plan=plan,
            consent=consent,
            assessment=assessment,
            triage=triage,
            evidence=evidence,
            medication=medication,
            human_request=human_request,
        )
        self._record(
            messages,
            ledger,
            case,
            AgentRole.SUMMARIZER,
            AgentRole.HUMAN_REVIEW,
            MessageKind.SUMMARY_READY,
            SummaryReady(
                summary_title=summary.title,
                citation_count=len(summary.citations),
            ),
            {"citation_count": len(summary.citations)},
        )

        status = (
            RunStatus.AWAITING_HUMAN_REVIEW
            if assessment.requires_human
            else RunStatus.COMPLETED
        )
        return RunResult(
            case_id=case.case_id,
            status=status,
            redacted_narrative=redaction.text,
            plan=plan,
            consent=consent,
            policy=assessment,
            redaction=redaction.report,
            messages=tuple(messages),
            summary=summary,
            ledger=ledger.entries,
            audit=ledger.verify(),
            requires_human=assessment.requires_human,
        )

    @staticmethod
    def _record(
        messages: list[AgentMessage],
        ledger: AuditLedger,
        case: PatientCase,
        sender: AgentRole,
        recipient: AgentRole,
        kind: MessageKind,
        payload: object,
        details: dict[str, object],
    ) -> AgentMessage:
        message_id = f"MSG-{case.case_id}-{len(messages) + 1:03d}"
        message = AgentMessage(
            message_id=message_id,
            case_id=case.case_id,
            sender=sender,
            recipient=recipient,
            kind=kind,
            payload=payload,  # type: ignore[arg-type]
        )
        messages.append(message)
        ledger.append(
            sender.value,
            f"message.{kind.value}",
            {"message_id": message_id, **details},
        )
        return message

    @staticmethod
    def _empty_policy() -> PolicyAssessment:
        return PolicyAssessment(
            findings=(),
            verdict=Verdict.ALLOW,
            requires_human=False,
        )

    @staticmethod
    def _consent_refusal(
        case: PatientCase,
        redaction: RedactionResult,
        plan: RoutingPlan,
        consent: tuple[ConsentDecision, ...],
        denied: tuple[ConsentDecision, ...],
    ) -> Summary:
        denied_lines = "\n".join(
            f"- {decision.role.label}: {decision.reason}" for decision in denied
        )
        return Summary(
            title=f"Consent Denied — {case.case_id}",
            status="blocked — consent required",
            sections=(
                SummarySection(
                    heading="Authorization",
                    body=(
                        "Orchestration stopped before any agent processed the case. "
                        "The following scopes were not granted:\n\n" + denied_lines
                    ),
                ),
                SummarySection(
                    heading="Routing",
                    body="\n".join(
                        f"- {decision.role.label}: {decision.rationale}"
                        for decision in plan.decisions
                    ),
                ),
                SummarySection(
                    heading="Redacted Case Snapshot",
                    body=f"Age {case.age}. Narrative: {redaction.text}",
                ),
            ),
            citations=(),
            disclaimers=DISCLAIMERS,
        )

    @staticmethod
    def _safety_refusal(
        case: PatientCase,
        redaction: RedactionResult,
        assessment: PolicyAssessment,
    ) -> Summary:
        finding_lines = "\n".join(
            (
                f"- **{finding.rule_id}** ({finding.severity.value}) — "
                f"{finding.verdict.value}: {finding.rationale}"
            )
            for finding in assessment.findings
        )
        citations = tuple(
            Citation(
                identifier=finding.rule_id,
                title=f"Policy rule {finding.rule_id} ({finding.category})",
                source="ieesbots deterministic safety policy engine",
                kind="policy",
            )
            for finding in assessment.findings
        )
        return Summary(
            title=f"Safety Block — {case.case_id}",
            status="blocked — safety policy",
            sections=(
                SummarySection(
                    heading="Blocking Findings",
                    body=(
                        "The deterministic safety policy blocked this case. No "
                        "clinical guidance or medication recommendation was "
                        "generated.\n\n" + finding_lines
                    ),
                ),
                SummarySection(
                    heading="Redacted Case Snapshot",
                    body=(
                        f"Age {case.age}. Symptoms: "
                        f"{', '.join(case.symptoms) or 'none recorded'}. "
                        f"Narrative: {redaction.text}"
                    ),
                ),
                SummarySection(
                    heading="Required Next Step",
                    body=(
                        "A licensed clinician and pharmacist must review the raw "
                        "case outside this prototype. Do not act on this artifact."
                    ),
                ),
            ),
            citations=citations,
            disclaimers=DISCLAIMERS,
        )
