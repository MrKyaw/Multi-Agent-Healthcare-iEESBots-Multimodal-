"""Custom exception hierarchy for the iEESBots governance core."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from .models import AgentRole, ConsentScope, PolicyFinding, Verdict


class IeesBotsError(Exception):
    """Base class for all package-specific failures."""


class CaseValidationError(IeesBotsError):
    """Raised when a synthetic case document is structurally invalid."""


class ConsentDeniedError(IeesBotsError):
    """Raised when an agent is invoked without its required consent scope."""

    def __init__(self, role: "AgentRole", scope: "ConsentScope", reason: str) -> None:
        self.role = role
        self.scope = scope
        self.reason = reason
        super().__init__(f"consent denied for {role.value}: {reason}")


class PolicyViolationError(IeesBotsError):
    """Raised when a caller attempts to bypass a blocked safety verdict."""

    def __init__(self, verdict: "Verdict", findings: tuple["PolicyFinding", ...]) -> None:
        self.verdict = verdict
        self.findings = findings
        rules = ", ".join(finding.rule_id for finding in findings)
        super().__init__(f"policy verdict {verdict.value} for rules: {rules}")


class AuditIntegrityError(IeesBotsError):
    """Raised when an audit chain fails verification."""
