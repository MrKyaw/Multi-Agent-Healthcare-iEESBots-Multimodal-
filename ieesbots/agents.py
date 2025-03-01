"""Deterministic agent implementations and the cited summarizer.

These are *rule-based stand-ins* for the original LLM-backed CrewAI agents.  They
exist so governance behavior can be tested without network access, API keys, or
non-determinism.  A live CrewAI/Ollama adapter can be layered on top later, but
it is not required for this repository's tests.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from .clinical_rules import allergy_conflicts, is_polypharmacy, matching_red_flags
from .contracts import (
    EvidenceBundle,
    HumanReviewRequest,
    MedicationReview,
    TriageReport,
)
from .models import (
    Citation,
    ConsentDecision,
    PatientCase,
    PolicyAssessment,
    RoutingPlan,
    Severity,
    Summary,
    SummarySection,
)
from .redaction import RedactionResult

#: Repeated in every automated summary.  This package is a research prototype.
DISCLAIMERS: tuple[str, ...] = (
    "Synthetic research prototype only — this is not a medical device.",
    "No diagnosis, prescription, or treatment decision is produced.",
    "All cases and evidence are fictional; no real patient data is used.",
    "A licensed clinician must review every escalation before any action.",
    "Not validated for clinical use; do not deploy in a care setting.",
)

_ACUITY_ACTIONS: dict[str, tuple[str, ...]] = {
    "critical": (
        "Escalate immediately to emergency clinical review.",
        "Do not provide automated reassurance or self-care advice.",
    ),
    "urgent": (
        "Arrange same-day clinician assessment.",
        "Keep the synthetic case open until reviewed.",
    ),
    "semi-urgent": (
        "Route to a clinician within the configured service window.",
        "Ask the reviewer to confirm the symptom timeline.",
    ),
    "routine": (
        "Queue for routine human review of the synthetic case.",
        "No urgent escalation was triggered by the rules.",
    ),
}

_WORD_PATTERN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> frozenset[str]:
    """Tokenize lowercase text for deterministic keyword retrieval."""

    return frozenset(_WORD_PATTERN.findall(text.lower()))


class TriageAgent:
    """Rule-based triage that reports acuity and red flags."""

    def assess(self, case: PatientCase) -> TriageReport:
        """Return a deterministic acuity assessment."""

        matches = matching_red_flags(case)
        has_critical = any(
            match.severity is Severity.CRITICAL for match in matches
        )
        if has_critical:
            acuity = "critical"
        elif matches:
            acuity = "urgent"
        elif len(case.symptoms) >= 3:
            acuity = "semi-urgent"
        else:
            acuity = "routine"
        if matches:
            rationale = (
                f"{len(matches)} red-flag term(s) matched; human escalation is "
                "mandatory before any guidance."
            )
        else:
            rationale = (
                f"No red-flag terms matched across {len(case.symptoms)} reported "
                "symptom(s); routine human review applies."
            )
        return TriageReport(
            acuity=acuity,
            red_flags=tuple(f"{match.term} [{match.rule_id}]" for match in matches),
            rationale=rationale,
            recommended_actions=_ACUITY_ACTIONS[acuity],
        )


class EvidenceAgent:
    """Keyword retriever over a small, caller-supplied synthetic bundle."""

    def retrieve(
        self, case: PatientCase, query: Optional[str] = None
    ) -> EvidenceBundle:
        """Retrieve evidence items overlapping the symptom/query tokens."""

        effective_query = query if query is not None else ", ".join(case.symptoms)
        terms = tokenize(effective_query)
        matched = tuple(
            item
            for item in case.evidence
            if terms & tokenize(item.searchable_text())
        )
        if matched:
            coverage = "complete"
            note = f"{len(matched)} synthetic evidence item(s) matched the query."
        elif case.evidence:
            coverage = "fallback"
            note = (
                "No keyword overlap; the full synthetic bundle is returned for "
                "human review rather than silently dropping evidence."
            )
            matched = case.evidence
        else:
            coverage = "missing"
            note = "No synthetic evidence bundle was supplied with this case."
        return EvidenceBundle(
            query=effective_query,
            matched_ids=tuple(item.evidence_id for item in matched),
            coverage=coverage,
            note=note,
        )


class MedicationAgent:
    """Detect allergy conflicts and polypharmacy without prescribing."""

    def review(self, case: PatientCase) -> MedicationReview:
        """Return medication-safety observations for human review."""

        conflicts = allergy_conflicts(case)
        polypharmacy = is_polypharmacy(case)
        conflict_labels = tuple(
            f"{allergy} allergy vs {medication}" for allergy, medication in conflicts
        )
        if conflicts:
            recommendation = (
                "Do not administer the conflicting medication; escalate to a "
                "pharmacist and prescriber before any medication guidance."
            )
        elif polypharmacy:
            recommendation = (
                "Polypharmacy threshold reached; obtain pharmacist review of the "
                "synthetic medication list."
            )
        else:
            recommendation = (
                "No rule-level allergy conflict detected; a human must still "
                "verify the medication list."
            )
        return MedicationReview(
            conflicts=conflict_labels,
            polypharmacy=polypharmacy,
            recommendation=recommendation,
        )


class HumanReviewAgent:
    """Create the escalation packet that gates finalization."""

    def request(
        self, case: PatientCase, assessment: PolicyAssessment
    ) -> HumanReviewRequest:
        """Build a reviewer-facing reason and question list."""

        if assessment.findings:
            reason = " ".join(
                f"{finding.rule_id}: {finding.rationale}"
                for finding in assessment.findings
            )
        else:
            reason = "Routine human confirmation requested for the synthetic case."
        return HumanReviewRequest(
            reason=reason,
            questions=(
                "Does this synthetic case require immediate in-person assessment?",
                "Is the medication and allergy list complete and verified?",
                "Is the cited evidence sufficient for the reviewer's decision?",
            ),
        )


class SummarizerAgent:
    """Compose a structured, cited draft summary with disclaimers."""

    def summarize(
        self,
        case: PatientCase,
        redaction: RedactionResult,
        plan: RoutingPlan,
        consent: tuple[ConsentDecision, ...],
        assessment: PolicyAssessment,
        triage: TriageReport,
        evidence: Optional[EvidenceBundle] = None,
        medication: Optional[MedicationReview] = None,
        human_request: Optional[HumanReviewRequest] = None,
    ) -> Summary:
        """Build a summary referencing every routed agent and policy finding."""

        sections = [
            SummarySection(
                heading="Synthetic Case Snapshot",
                body=(
                    f"Case `{case.case_id}`; age {case.age}. "
                    f"Symptoms: {', '.join(case.symptoms) or 'none recorded'}. "
                    f"Redacted narrative: {redaction.text}"
                ),
            ),
            SummarySection(
                heading="Routing and Consent",
                body="\n".join(
                    [
                        (
                            f"- {decision.role.label} (priority {decision.priority}): "
                            f"{decision.rationale}"
                        )
                        for decision in plan.decisions
                    ]
                    + [
                        (
                            f"- Consent {decision.role.label}: "
                            f"{'granted' if decision.granted else 'denied'} "
                            f"({decision.reason})"
                        )
                        for decision in consent
                    ]
                ),
            ),
            SummarySection(
                heading="Triage",
                body=(
                    f"Acuity: **{triage.acuity}**. {triage.rationale}\n\n"
                    f"Red flags: {', '.join(triage.red_flags) or 'none'}\n\n"
                    "Recommended next steps:\n"
                    + "\n".join(f"- {action}" for action in triage.recommended_actions)
                ),
            ),
            SummarySection(
                heading="Evidence Review",
                body=self._evidence_body(evidence),
            ),
            SummarySection(
                heading="Medication Safety",
                body=self._medication_body(medication),
            ),
            SummarySection(
                heading="Safety Policy",
                body=self._policy_body(assessment),
            ),
            SummarySection(
                heading="Human Oversight",
                body=self._human_body(assessment, human_request),
            ),
        ]

        citations = self._citations(case, assessment, evidence)
        status = (
            f"{assessment.verdict.value} — human review required"
            if assessment.requires_human
            else assessment.verdict.value
        )
        return Summary(
            title=f"Synthetic Care Navigation Summary — {case.case_id}",
            status=status,
            sections=tuple(sections),
            citations=citations,
            disclaimers=DISCLAIMERS,
        )

    @staticmethod
    def _evidence_body(evidence: Optional[EvidenceBundle]) -> str:
        if evidence is None:
            return (
                "No evidence agent was routed for this case. Clinical claims are "
                "therefore not grounded in the synthetic evidence bundle."
            )
        ids = ", ".join(evidence.matched_ids) or "none"
        return (
            f"Retrieval coverage: **{evidence.coverage}**. "
            f"Matched synthetic evidence: {ids}. {evidence.note}"
        )

    @staticmethod
    def _medication_body(medication: Optional[MedicationReview]) -> str:
        if medication is None:
            return (
                "No medication agent was routed; medication safety was not "
                "independently checked by the deterministic rules."
            )
        conflicts = ", ".join(medication.conflicts) or "none detected"
        return (
            f"Allergy conflicts: {conflicts}. "
            f"Polypharmacy threshold reached: {medication.polypharmacy}. "
            f"{medication.recommendation}"
        )

    @staticmethod
    def _policy_body(assessment: PolicyAssessment) -> str:
        if not assessment.findings:
            return "No deterministic policy findings; human review still applies."
        lines = [
            (
                f"- **{finding.rule_id}** ({finding.category}, "
                f"{finding.severity.value}) — {finding.verdict.value}: "
                f"{finding.rationale}"
            )
            for finding in assessment.findings
        ]
        return (
            f"Final verdict: **{assessment.verdict.value}**. "
            f"Human review required: {assessment.requires_human}.\n\n"
            + "\n".join(lines)
        )

    @staticmethod
    def _human_body(
        assessment: PolicyAssessment,
        human_request: Optional[HumanReviewRequest],
    ) -> str:
        if human_request is not None:
            return (
                "This draft is **not final**. A licensed human reviewer must "
                f"resolve the escalation.\n\nReviewer packet: {human_request.reason}"
            )
        if assessment.requires_human:
            return (
                "Policy requires human review, but no reviewer packet was produced. "
                "This is an internal inconsistency and must be investigated."
            )
        return (
            "No human-review packet was generated because the policy verdict was "
            "allow. The summary remains a synthetic research artifact."
        )

    @staticmethod
    def _citations(
        case: PatientCase,
        assessment: PolicyAssessment,
        evidence: Optional[EvidenceBundle],
    ) -> tuple[Citation, ...]:
        evidence_by_id = {item.evidence_id: item for item in case.evidence}
        cited_ids: Iterable[str] = (
            evidence.matched_ids if evidence is not None else ()
        )
        citations = [
            Citation(
                identifier=evidence_id,
                title=evidence_by_id[evidence_id].title,
                source=evidence_by_id[evidence_id].source,
                kind="synthetic_evidence",
            )
            for evidence_id in cited_ids
            if evidence_id in evidence_by_id
        ]
        citations.extend(
            Citation(
                identifier=finding.rule_id,
                title=f"Policy rule {finding.rule_id} ({finding.category})",
                source="ieesbots deterministic safety policy engine",
                kind="policy",
            )
            for finding in assessment.findings
        )
        return tuple(citations)
