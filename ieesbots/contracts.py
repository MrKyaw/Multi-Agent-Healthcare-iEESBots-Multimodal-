"""Typed message contracts exchanged between synthetic agents.

The contracts are deliberately small and serializable.  Each payload declares
exactly what its producing agent is allowed to report, which keeps the
orchestrator from passing unstructured dictionaries between roles.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Union

from .models import AgentRole


class MessageKind(str, Enum):
    """Kinds of inter-agent messages in the workflow."""

    TRIAGE_REPORT = "triage_report"
    EVIDENCE_BUNDLE = "evidence_bundle"
    MEDICATION_REVIEW = "medication_review"
    HUMAN_REVIEW_REQUEST = "human_review_request"
    SUMMARY_READY = "summary_ready"


@dataclass(frozen=True)
class TriageReport:
    """Deterministic acuity assessment produced by the triage agent."""

    acuity: str
    red_flags: tuple[str, ...]
    rationale: str
    recommended_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceBundle:
    """Result of a retrieval request over synthetic evidence items."""

    query: str
    matched_ids: tuple[str, ...]
    coverage: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MedicationReview:
    """Medication-safety observations; never a prescribing recommendation."""

    conflicts: tuple[str, ...]
    polypharmacy: bool
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HumanReviewRequest:
    """Escalation packet for a licensed human reviewer."""

    reason: str
    questions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SummaryReady:
    """Notification that a cited draft summary is available."""

    summary_title: str
    citation_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


MessagePayload = Union[
    TriageReport,
    EvidenceBundle,
    MedicationReview,
    HumanReviewRequest,
    SummaryReady,
]


@dataclass(frozen=True)
class AgentMessage:
    """Envelope around a typed payload, with sender/recipient routing."""

    message_id: str
    case_id: str
    sender: AgentRole
    recipient: AgentRole
    kind: MessageKind
    payload: MessagePayload

    def to_dict(self) -> dict[str, Any]:
        """Serialize the envelope and payload for audit and JSON output."""

        return {
            "message_id": self.message_id,
            "case_id": self.case_id,
            "sender": self.sender.value,
            "recipient": self.recipient.value,
            "kind": self.kind.value,
            "payload": self.payload.to_dict(),
        }
