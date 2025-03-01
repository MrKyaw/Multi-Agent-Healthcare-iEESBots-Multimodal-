"""Deterministic agent router with explicit precedence.

Routing is a pure function of structured case flags and already-structured
fields (medications, evidence).  No language model participates, so the same
case always produces the same plan and the same rationale string.

Precedence is expressed as ascending priority numbers: lower runs first.
Triage always runs, evidence and medication may run in parallel in a real
deployment, human review gates finalization, and the summarizer always runs
last to produce the cited draft.
"""

from __future__ import annotations

from .models import (
    AgentRole,
    CaseFlags,
    ConsentScope,
    PatientCase,
    RoutingDecision,
    RoutingPlan,
)

TRIAGE_PRIORITY = 10
EVIDENCE_PRIORITY = 20
MEDICATION_PRIORITY = 30
HUMAN_REVIEW_PRIORITY = 40
SUMMARIZER_PRIORITY = 90


class AgentRouter:
    """Select agents for a synthetic case using documented, ordered rules."""

    def route(self, case: PatientCase) -> RoutingPlan:
        """Build an ordered routing plan for ``case``.

        All matching rules contribute their rationale; they are not mutually
        exclusive.  Ordering is by ascending priority and is stable.
        """

        decisions = [
            RoutingDecision(
                role=AgentRole.TRIAGE,
                priority=TRIAGE_PRIORITY,
                rationale="Triage is mandatory for every case.",
                required_scope=ConsentScope.CARE_TRIAGE,
            ),
            RoutingDecision(
                role=AgentRole.SUMMARIZER,
                priority=SUMMARIZER_PRIORITY,
                rationale="A cited draft summary is always produced.",
                required_scope=ConsentScope.SUMMARY_GENERATION,
            ),
        ]

        evidence_reasons = self._evidence_reasons(case.flags, case)
        if evidence_reasons:
            decisions.append(
                RoutingDecision(
                    role=AgentRole.EVIDENCE,
                    priority=EVIDENCE_PRIORITY,
                    rationale="; ".join(evidence_reasons),
                    required_scope=ConsentScope.EVIDENCE_RETRIEVAL,
                )
            )

        medication_reasons = self._medication_reasons(case)
        if medication_reasons:
            decisions.append(
                RoutingDecision(
                    role=AgentRole.MEDICATION,
                    priority=MEDICATION_PRIORITY,
                    rationale="; ".join(medication_reasons),
                    required_scope=ConsentScope.MEDICATION_REVIEW,
                )
            )

        human_reasons = self._human_review_reasons(case.flags, case)
        if human_reasons:
            decisions.append(
                RoutingDecision(
                    role=AgentRole.HUMAN_REVIEW,
                    priority=HUMAN_REVIEW_PRIORITY,
                    rationale="; ".join(human_reasons),
                    required_scope=ConsentScope.HUMAN_REVIEW,
                )
            )

        decisions.sort(key=lambda decision: decision.priority)
        return RoutingPlan(decisions=tuple(decisions))

    @staticmethod
    def _evidence_reasons(flags: CaseFlags, case: PatientCase) -> list[str]:
        reasons = []
        if flags.imaging_available:
            reasons.append("Imaging is available for review")
        if flags.chest_pain:
            reasons.append("Chest pain requires evidence-backed escalation")
        if case.evidence:
            reasons.append("A synthetic evidence bundle was supplied")
        return reasons

    @staticmethod
    def _medication_reasons(case: PatientCase) -> list[str]:
        reasons = []
        if case.flags.polypharmacy:
            reasons.append("Polypharmacy flag is set")
        if len(case.medications) >= 2:
            reasons.append("Multiple medications require interaction review")
        if case.allergies:
            reasons.append("Allergies require medication conflict review")
        return reasons

    @staticmethod
    def _human_review_reasons(flags: CaseFlags, case: PatientCase) -> list[str]:
        reasons = []
        if flags.chest_pain:
            reasons.append("Chest pain is a time-sensitive presentation")
        if flags.mental_health_crisis:
            reasons.append("Mental-health crisis requires immediate human support")
        if flags.pregnancy:
            reasons.append("Pregnancy changes medication and imaging safety")
        if flags.pediatric:
            reasons.append("Pediatric case requires age-specific review")
        if case.age >= 75:
            reasons.append("Age 75+ triggers a frailty review")
        return reasons
