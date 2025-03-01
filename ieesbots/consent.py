"""Least-privilege consent and authorization gate.

Each agent role maps to exactly one required consent scope.  A missing scope
produces a denial decision with a stable audit reason rather than an exception,
so the orchestrator can halt cleanly and preserve evidence of *why* it halted.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from .models import (
    AgentRole,
    ConsentDecision,
    ConsentScope,
    RoutingPlan,
)


#: Default minimum scope required to invoke each role.
REQUIRED_SCOPES: Mapping[AgentRole, ConsentScope] = {
    AgentRole.TRIAGE: ConsentScope.CARE_TRIAGE,
    AgentRole.EVIDENCE: ConsentScope.EVIDENCE_RETRIEVAL,
    AgentRole.MEDICATION: ConsentScope.MEDICATION_REVIEW,
    AgentRole.HUMAN_REVIEW: ConsentScope.HUMAN_REVIEW,
    AgentRole.SUMMARIZER: ConsentScope.SUMMARY_GENERATION,
}


class ConsentGate:
    """Authorize agent invocations against granted consent scopes."""

    def __init__(
        self, required: Mapping[AgentRole, ConsentScope] | None = None
    ) -> None:
        self._required = required if required is not None else REQUIRED_SCOPES

    def authorize(
        self, role: AgentRole, granted: Iterable[ConsentScope]
    ) -> ConsentDecision:
        """Authorize one role, returning a decision instead of raising."""

        scope = self._required.get(role)
        if scope is None:
            raise ValueError(f"no consent requirement configured for {role.value}")
        granted_set = frozenset(granted)
        allowed = scope in granted_set
        reason = (
            f"scope '{scope.value}' present"
            if allowed
            else f"missing required scope '{scope.value}'"
        )
        return ConsentDecision(role=role, scope=scope, granted=allowed, reason=reason)

    def authorize_plan(
        self, plan: RoutingPlan, granted: Iterable[ConsentScope]
    ) -> tuple[ConsentDecision, ...]:
        """Authorize every role in a plan in execution order."""

        granted_set = frozenset(granted)
        return tuple(
            self.authorize(decision.role, granted_set) for decision in plan.decisions
        )

    @staticmethod
    def denied(decisions: tuple[ConsentDecision, ...]) -> tuple[ConsentDecision, ...]:
        """Return only denied decisions, preserving order."""

        return tuple(decision for decision in decisions if not decision.granted)
