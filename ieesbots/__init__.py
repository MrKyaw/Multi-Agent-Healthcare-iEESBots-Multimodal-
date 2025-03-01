"""iEESBots — deterministic governance core for synthetic multi-agent care flows.

This package is an offline, dependency-free research prototype.  It is **not a
medical device**, does not provide medical advice, and uses only synthetic data.
"""

from __future__ import annotations

from .agents import (
    DISCLAIMERS,
    EvidenceAgent,
    HumanReviewAgent,
    MedicationAgent,
    SummarizerAgent,
    TriageAgent,
)
from .audit import AuditLedger, GENESIS_HASH, utc_now
from .casefile import case_from_dict, demo_case, load_case
from .clinical_rules import (
    ALLERGY_FAMILIES,
    RED_FLAG_TERMS,
    allergy_conflicts,
    is_polypharmacy,
    matching_red_flags,
)
from .consent import REQUIRED_SCOPES, ConsentGate
from .contracts import (
    AgentMessage,
    EvidenceBundle,
    HumanReviewRequest,
    MedicationReview,
    MessageKind,
    SummaryReady,
    TriageReport,
)
from .exceptions import (
    AuditIntegrityError,
    CaseValidationError,
    ConsentDeniedError,
    IeesBotsError,
    PolicyViolationError,
)
from .models import (
    AgentRole,
    AuditEntry,
    AuditVerification,
    CaseFlags,
    Citation,
    ConsentDecision,
    ConsentScope,
    EvidenceItem,
    PatientCase,
    PolicyAssessment,
    PolicyFinding,
    RedactionReport,
    RoutingDecision,
    RoutingPlan,
    RunResult,
    RunStatus,
    Severity,
    Summary,
    SummarySection,
    Verdict,
)
from .orchestrator import Orchestrator
from .policy import SafetyPolicyEngine
from .redaction import (
    DEFAULT_PATTERNS,
    PHIKind,
    PhiVault,
    RedactionResult,
    Redactor,
)
from .router import AgentRouter

__version__ = "1.0.0"
__author__ = "Kyaw Kyaw Oo"

__all__ = [
    "ALLERGY_FAMILIES",
    "AgentMessage",
    "AgentRole",
    "AgentRouter",
    "AuditEntry",
    "AuditIntegrityError",
    "AuditLedger",
    "AuditVerification",
    "CaseFlags",
    "CaseValidationError",
    "Citation",
    "ConsentDecision",
    "ConsentDeniedError",
    "ConsentGate",
    "ConsentScope",
    "DEFAULT_PATTERNS",
    "DISCLAIMERS",
    "EvidenceAgent",
    "EvidenceBundle",
    "EvidenceItem",
    "GENESIS_HASH",
    "HumanReviewAgent",
    "HumanReviewRequest",
    "IeesBotsError",
    "MedicationAgent",
    "MedicationReview",
    "MessageKind",
    "Orchestrator",
    "PHIKind",
    "PatientCase",
    "PhiVault",
    "PolicyAssessment",
    "PolicyFinding",
    "PolicyViolationError",
    "REQUIRED_SCOPES",
    "RED_FLAG_TERMS",
    "RedactionReport",
    "RedactionResult",
    "Redactor",
    "RoutingDecision",
    "RoutingPlan",
    "RunResult",
    "RunStatus",
    "SafetyPolicyEngine",
    "Severity",
    "SummarizerAgent",
    "Summary",
    "SummaryReady",
    "SummarySection",
    "TriageAgent",
    "TriageReport",
    "Verdict",
    "allergy_conflicts",
    "case_from_dict",
    "demo_case",
    "is_polypharmacy",
    "load_case",
    "matching_red_flags",
    "utc_now",
]
