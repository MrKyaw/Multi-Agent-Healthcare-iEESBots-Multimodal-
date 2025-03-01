"""Tests for the deterministic iEESBots governance core.

These tests cover every public function and both sides of every branch in the
``ieesbots`` package.  They use only synthetic data and run fully offline.
"""

from __future__ import annotations

import importlib
import json
import runpy
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from ieesbots import (
    ALLERGY_FAMILIES,
    DEFAULT_PATTERNS,
    DISCLAIMERS,
    GENESIS_HASH,
    RED_FLAG_TERMS,
    AgentMessage,
    AgentRole,
    AgentRouter,
    AuditIntegrityError,
    AuditLedger,
    AuditVerification,
    CaseFlags,
    CaseValidationError,
    Citation,
    ConsentDecision,
    ConsentDeniedError,
    ConsentGate,
    ConsentScope,
    EvidenceAgent,
    EvidenceBundle,
    EvidenceItem,
    HumanReviewAgent,
    HumanReviewRequest,
    IeesBotsError,
    MedicationAgent,
    MedicationReview,
    MessageKind,
    Orchestrator,
    PHIKind,
    PatientCase,
    PhiVault,
    PolicyAssessment,
    PolicyFinding,
    PolicyViolationError,
    RedactionReport,
    RedactionResult,
    Redactor,
    RoutingDecision,
    RunResult,
    RunStatus,
    SafetyPolicyEngine,
    Severity,
    SummarizerAgent,
    Summary,
    SummaryReady,
    SummarySection,
    TriageAgent,
    TriageReport,
    Verdict,
    allergy_conflicts,
    case_from_dict,
    demo_case,
    is_polypharmacy,
    load_case,
    matching_red_flags,
    utc_now,
)
from ieesbots import cli as cli_module
from ieesbots.audit import _digest
from ieesbots.casefile import _evidence_from_mapping

ALL_SCOPES = frozenset(ConsentScope)


def make_case(**overrides: object) -> PatientCase:
    """Build a benign synthetic case with all consent scopes by default."""

    defaults: dict[str, object] = {
        "case_id": "SYN-T-001",
        "narrative": "Synthetic patient reports fatigue. No identifiers present.",
        "age": 45,
        "symptoms": ("fatigue",),
        "medications": ("metformin",),
        "allergies": (),
        "evidence": (),
        "flags": CaseFlags(),
        "consent_scopes": ALL_SCOPES,
    }
    defaults.update(overrides)
    return PatientCase(**defaults)  # type: ignore[arg-type]


def make_evidence(**overrides: object) -> EvidenceItem:
    defaults: dict[str, object] = {
        "evidence_id": "EV-T-1",
        "title": "Synthetic fatigue checklist",
        "source": "fictional test fixture",
        "text": "Synthetic guidance about fatigue and clinician review.",
        "kind": "checklist",
    }
    defaults.update(overrides)
    return EvidenceItem(**defaults)  # type: ignore[arg-type]


def make_case_document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "case_id": "SYN-FILE-1",
        "narrative": "Synthetic file case with fatigue only.",
        "age": 41,
        "symptoms": ["fatigue"],
        "medications": ["metformin"],
        "consent": [scope.value for scope in ConsentScope],
    }
    document.update(overrides)
    return document


# ---------------------------------------------------------------------------
# Models, enums, and serialization
# ---------------------------------------------------------------------------


class TestModels:
    def test_role_labels(self) -> None:
        assert AgentRole.TRIAGE.label == "Triage"
        assert AgentRole.EVIDENCE.label == "Evidence"
        assert AgentRole.MEDICATION.label == "Medication"
        assert AgentRole.HUMAN_REVIEW.label == "Human Review"
        assert AgentRole.SUMMARIZER.label == "Summarizer"

    def test_case_flags_defaults(self) -> None:
        flags = CaseFlags()
        assert not any(
            [
                flags.chest_pain,
                flags.polypharmacy,
                flags.imaging_available,
                flags.mental_health_crisis,
                flags.pregnancy,
                flags.pediatric,
            ]
        )

    def test_patient_case_validation_rejects_empty_id(self) -> None:
        with pytest.raises(CaseValidationError, match="case_id"):
            make_case(case_id="  ")

    @pytest.mark.parametrize("age", [-1, 131])
    def test_patient_case_validation_rejects_age(self, age: int) -> None:
        with pytest.raises(CaseValidationError, match="age"):
            make_case(age=age)

    def test_patient_case_accepts_boundary_ages(self) -> None:
        assert make_case(age=0).age == 0
        assert make_case(age=130).age == 130

    def test_evidence_searchable_text(self) -> None:
        item = make_evidence(title="Mixed Case", text="Chest Pain")
        assert item.searchable_text() == "mixed case chest pain"

    def test_routing_plan_properties(self) -> None:
        plan = AgentRouter().route(make_case())
        assert plan.roles == (AgentRole.TRIAGE, AgentRole.SUMMARIZER)
        assert plan.scopes == (
            ConsentScope.CARE_TRIAGE,
            ConsentScope.SUMMARY_GENERATION,
        )

    def test_policy_assessment_reason_properties(self) -> None:
        findings = (
            PolicyFinding(
                "RF-001", "red_flag", Severity.CRITICAL, Verdict.ESCALATE, "x"
            ),
            PolicyFinding("ALG-001", "allergy", Severity.CRITICAL, Verdict.BLOCK, "y"),
            PolicyFinding("MED-001", "polypharmacy", Severity.HIGH, Verdict.ALLOW, "z"),
        )
        assessment = PolicyAssessment(findings, Verdict.BLOCK, True)
        assert assessment.blocked_reasons == ("ALG-001",)
        assert assessment.escalation_reasons == ("RF-001",)

    def test_summary_render_and_dict(self) -> None:
        summary = Summary(
            title="Synthetic Summary",
            status="allow",
            sections=(SummarySection("One", "Body"),),
            citations=(Citation("EV-1", "Title", "Source", "synthetic_evidence"),),
            disclaimers=("Not a device.",),
        )
        rendered = summary.render()
        assert "# Synthetic Summary" in rendered
        assert "[EV-1] Title — Source" in rendered
        assert "- Not a device." in rendered
        assert rendered.endswith("\n")
        payload = summary.to_dict()
        assert payload["citations"][0]["identifier"] == "EV-1"
        assert payload["sections"][0]["heading"] == "One"

    def test_summary_without_citations_renders_headers(self) -> None:
        summary = Summary("T", "blocked", (), (), ("Disclaimer",))
        rendered = summary.render()
        assert "## Citations" in rendered
        assert "## Disclaimers" in rendered

    def test_audit_models_to_dict(self) -> None:
        entry = AuditLedger(clock=lambda: "t").append("actor", "action", {"a": 1})
        assert entry.to_dict()["details"] == {"a": 1}
        verification = AuditVerification(True, None, "ok")
        assert verification.to_dict() == {
            "valid": True,
            "broken_index": None,
            "reason": "ok",
        }

    def test_redaction_report_to_dict(self) -> None:
        report = RedactionReport({"mrn": 2}, 2)
        assert report.to_dict() == {"counts": {"mrn": 2}, "total": 2}

    def test_contract_payloads_serialize(self) -> None:
        triage = TriageReport("routine", (), "none", ("review",))
        assert triage.to_dict()["acuity"] == "routine"
        evidence = EvidenceBundle("q", ("EV-1",), "complete", "note")
        assert evidence.to_dict()["matched_ids"] == ("EV-1",)
        medication = MedicationReview((), False, "review")
        assert medication.to_dict()["polypharmacy"] is False
        human = HumanReviewRequest("reason", ("question",))
        assert human.to_dict()["questions"] == ("question",)
        ready = SummaryReady("title", 2)
        assert ready.to_dict()["citation_count"] == 2

    def test_agent_message_serializes(self) -> None:
        message = AgentMessage(
            message_id="MSG-1",
            case_id="SYN-1",
            sender=AgentRole.TRIAGE,
            recipient=AgentRole.SUMMARIZER,
            kind=MessageKind.TRIAGE_REPORT,
            payload=TriageReport("routine", (), "none", ("review",)),
        )
        payload = message.to_dict()
        assert payload["sender"] == "triage"
        assert payload["recipient"] == "summarizer"
        assert payload["kind"] == "triage_report"
        assert payload["payload"]["acuity"] == "routine"

    def test_exception_messages(self) -> None:
        denied = ConsentDeniedError(
            AgentRole.TRIAGE, ConsentScope.CARE_TRIAGE, "missing"
        )
        assert "triage" in str(denied)
        assert denied.scope is ConsentScope.CARE_TRIAGE
        finding = PolicyFinding(
            "ALG-001", "allergy", Severity.CRITICAL, Verdict.BLOCK, "conflict"
        )
        violation = PolicyViolationError(Verdict.BLOCK, (finding,))
        assert violation.verdict is Verdict.BLOCK
        assert "ALG-001" in str(violation)
        assert isinstance(violation, IeesBotsError)


# ---------------------------------------------------------------------------
# PHI redaction and vault
# ---------------------------------------------------------------------------


class TestRedaction:
    def test_redacts_all_identifier_categories(self) -> None:
        text = (
            "MRN: 1234567 phone (555) 123-4567 email jane@example.test "
            "SSN 123-45-6789 visit 2026-01-15 and 1/2/2025"
        )
        redactor = Redactor()
        result = redactor.redact(text)
        assert "1234567" not in result.text
        assert "555" not in result.text
        assert "jane@example.test" not in result.text
        assert "123-45-6789" not in result.text
        assert "2026-01-15" not in result.text
        assert "1/2/2025" not in result.text
        assert result.report.total == 6
        assert result.report.counts == {
            "mrn": 1,
            "phone": 1,
            "email": 1,
            "ssn": 1,
            "date": 2,
        }
        assert len(redactor.vault) == 6
        assert redactor.detokenize(result.text) == text

    def test_repeated_values_use_stable_tokens(self) -> None:
        redactor = Redactor()
        result = redactor.redact("MRN: 1234567 then MRN: 1234567")
        assert result.text.count("[[MRN_1]]") == 2
        assert result.report.total == 2
        assert len(redactor.vault) == 1
        assert redactor.vault.resolve("[[MRN_1]]") == "MRN: 1234567"

    def test_empty_text_produces_empty_report(self) -> None:
        result = Redactor().redact("")
        assert result.text == ""
        assert result.report.total == 0
        assert result.report.counts == {}

    def test_unknown_tokens_are_left_untouched(self) -> None:
        redactor = Redactor()
        assert redactor.detokenize("[[MRN_9]] mystery") == "[[MRN_9]] mystery"
        assert redactor.vault.resolve("[[MRN_9]]") is None

    def test_vault_tokens_and_counts(self) -> None:
        redactor = Redactor()
        redactor.redact("MRN: 1234567 and 555-123-4567")
        assert set(redactor.vault.tokens()) == {"[[MRN_1]]", "[[PHONE_1]]"}
        assert redactor.report_counts() == {"mrn": 1, "phone": 1}

    def test_custom_patterns_can_be_supplied(self) -> None:
        redactor = Redactor(patterns=())
        assert redactor.redact("MRN: 1234567").text == "MRN: 1234567"
        assert redactor.report_counts() == {}

    def test_default_patterns_cover_expected_kinds(self) -> None:
        assert [kind for kind, _ in DEFAULT_PATTERNS] == [
            PHIKind.EMAIL,
            PHIKind.MRN,
            PHIKind.SSN,
            PHIKind.PHONE,
            PHIKind.DATE,
        ]
        assert isinstance(PhiVault(), PhiVault)


# ---------------------------------------------------------------------------
# Consent gate
# ---------------------------------------------------------------------------


class TestConsent:
    def test_granted_scope(self) -> None:
        decision = ConsentGate().authorize(
            AgentRole.TRIAGE, {ConsentScope.CARE_TRIAGE}
        )
        assert decision.granted
        assert "present" in decision.reason

    def test_missing_scope_denied_with_audit_reason(self) -> None:
        decision = ConsentGate().authorize(AgentRole.MEDICATION, set())
        assert not decision.granted
        assert decision.scope is ConsentScope.MEDICATION_REVIEW
        assert "missing required scope" in decision.reason

    def test_authorize_plan_and_denied(self) -> None:
        plan = AgentRouter().route(make_case())
        decisions = ConsentGate().authorize_plan(
            plan, {ConsentScope.CARE_TRIAGE}
        )
        denied = ConsentGate.denied(decisions)
        assert [decision.role for decision in decisions] == list(plan.roles)
        assert [decision.role for decision in denied] == [AgentRole.SUMMARIZER]

    def test_unknown_role_raises(self) -> None:
        with pytest.raises(ValueError, match="no consent requirement"):
            ConsentGate(required={}).authorize(AgentRole.TRIAGE, ALL_SCOPES)

    def test_extra_scopes_do_not_grant_unrelated_roles(self) -> None:
        decision = ConsentGate().authorize(
            AgentRole.EVIDENCE, {ConsentScope.CARE_TRIAGE}
        )
        assert not decision.granted


# ---------------------------------------------------------------------------
# Router precedence and rationale
# ---------------------------------------------------------------------------


class TestRouter:
    def test_baseline_plan(self) -> None:
        plan = AgentRouter().route(make_case())
        assert plan.roles == (AgentRole.TRIAGE, AgentRole.SUMMARIZER)
        assert [decision.priority for decision in plan.decisions] == [10, 90]
        assert "mandatory" in plan.decisions[0].rationale

    def test_all_flags_select_agents_in_precedence_order(self) -> None:
        case = make_case(
            age=80,
            symptoms=("chest pain", "shortness of breath"),
            medications=("aspirin", "metoprolol"),
            allergies=("penicillin",),
            evidence=(make_evidence(),),
            flags=CaseFlags(
                chest_pain=True,
                polypharmacy=True,
                imaging_available=True,
                mental_health_crisis=True,
                pregnancy=True,
                pediatric=True,
            ),
        )
        plan = AgentRouter().route(case)
        assert plan.roles == (
            AgentRole.TRIAGE,
            AgentRole.EVIDENCE,
            AgentRole.MEDICATION,
            AgentRole.HUMAN_REVIEW,
            AgentRole.SUMMARIZER,
        )
        assert [decision.priority for decision in plan.decisions] == [
            10,
            20,
            30,
            40,
            90,
        ]
        rationale = " ".join(decision.rationale for decision in plan.decisions)
        assert "Imaging is available" in rationale
        assert "Chest pain requires evidence" in rationale
        assert "Polypharmacy flag" in rationale
        assert "Multiple medications" in rationale
        assert "Allergies require" in rationale
        assert "time-sensitive" in rationale
        assert "Mental-health crisis" in rationale
        assert "Pregnancy" in rationale
        assert "Pediatric" in rationale
        assert "Age 75+" in rationale

    def test_evidence_reason_from_supplied_bundle_only(self) -> None:
        plan = AgentRouter().route(make_case(evidence=(make_evidence(),)))
        assert AgentRole.EVIDENCE in plan.roles
        rationale = plan.decisions[1].rationale
        assert "bundle was supplied" in rationale
        assert "Imaging" not in rationale

    def test_evidence_reason_from_imaging_only(self) -> None:
        plan = AgentRouter().route(
            make_case(flags=CaseFlags(imaging_available=True))
        )
        assert AgentRole.EVIDENCE in plan.roles
        assert "Imaging" in plan.decisions[1].rationale

    def test_medication_reason_from_two_medications_only(self) -> None:
        plan = AgentRouter().route(
            make_case(medications=("metformin", "lisinopril"))
        )
        assert AgentRole.MEDICATION in plan.roles
        assert "Multiple medications" in plan.decisions[1].rationale

    def test_medication_reason_from_allergy_only(self) -> None:
        plan = AgentRouter().route(make_case(allergies=("penicillin",)))
        assert AgentRole.MEDICATION in plan.roles
        assert "Allergies require" in plan.decisions[1].rationale

    @pytest.mark.parametrize(
        ("flags", "age", "expected"),
        [
            (CaseFlags(pregnancy=True), 30, "Pregnancy"),
            (CaseFlags(pediatric=True), 30, "Pediatric"),
            (CaseFlags(mental_health_crisis=True), 30, "Mental-health"),
            (CaseFlags(), 75, "Age 75+"),
        ],
    )
    def test_individual_human_review_triggers(
        self, flags: CaseFlags, age: int, expected: str
    ) -> None:
        plan = AgentRouter().route(make_case(flags=flags, age=age))
        assert AgentRole.HUMAN_REVIEW in plan.roles
        human = plan.decisions[-2]
        assert human.role is AgentRole.HUMAN_REVIEW
        assert expected in human.rationale

    def test_chest_pain_selects_evidence_and_human(self) -> None:
        plan = AgentRouter().route(make_case(flags=CaseFlags(chest_pain=True)))
        assert plan.roles == (
            AgentRole.TRIAGE,
            AgentRole.EVIDENCE,
            AgentRole.HUMAN_REVIEW,
            AgentRole.SUMMARIZER,
        )


# ---------------------------------------------------------------------------
# Clinical rule primitives
# ---------------------------------------------------------------------------


class TestClinicalRules:
    def test_all_red_flag_terms_match(self) -> None:
        case = make_case(
            symptoms=(
                "chest pain",
                "shortness of breath",
                "suicidal ideation",
                "stroke symptoms",
                "severe bleeding",
            )
        )
        matches = matching_red_flags(case)
        assert {match.rule_id for match in matches} == {
            "RF-001",
            "RF-002",
            "RF-003",
            "RF-004",
            "RF-005",
        }
        assert all(match.term in RED_FLAG_TERMS for match in matches)

    def test_structured_flags_create_red_flags(self) -> None:
        case = make_case(
            symptoms=(),
            flags=CaseFlags(chest_pain=True, mental_health_crisis=True),
        )
        terms = [match.term for match in matching_red_flags(case)]
        assert terms == ["chest pain", "suicidal"]

    def test_no_red_flags(self) -> None:
        assert matching_red_flags(make_case()) == ()

    @pytest.mark.parametrize(
        ("allergy", "medication"),
        [
            ("penicillin", "amoxicillin"),
            ("penicillin", "penicillin g"),
            ("amox", "amoxicillin"),
            ("sulfa", "bactrim"),
            ("nsaid", "ibuprofen"),
            ("cephalosporin", "cephalexin"),
        ],
    )
    def test_allergy_conflicts_detected(
        self, allergy: str, medication: str
    ) -> None:
        case = make_case(allergies=(allergy,), medications=(medication,))
        assert allergy_conflicts(case) == ((allergy, medication),)

    def test_no_allergy_conflict(self) -> None:
        case = make_case(allergies=("shellfish",), medications=("metformin",))
        assert allergy_conflicts(case) == ()

    def test_empty_allergy_entries_are_ignored(self) -> None:
        case = make_case(
            allergies=("", "   ", "shellfish"), medications=("  ", "metformin")
        )
        assert allergy_conflicts(case) == ()

    def test_allergy_family_table_is_exposed(self) -> None:
        assert "penicillin" in ALLERGY_FAMILIES
        assert "amoxicillin" in ALLERGY_FAMILIES["penicillin"]

    @pytest.mark.parametrize(
        ("medications", "flag", "expected"),
        [
            ((), False, False),
            (("a", "b", "c", "d"), False, False),
            (("a", "b", "c", "d", "e"), False, True),
            (("a",), True, True),
        ],
    )
    def test_polypharmacy_threshold(
        self, medications: tuple[str, ...], flag: bool, expected: bool
    ) -> None:
        case = make_case(
            medications=medications, flags=CaseFlags(polypharmacy=flag)
        )
        assert is_polypharmacy(case) is expected


# ---------------------------------------------------------------------------
# Safety policy engine
# ---------------------------------------------------------------------------


class TestPolicy:
    def test_allow_for_benign_case(self) -> None:
        assessment = SafetyPolicyEngine().evaluate(make_case())
        assert assessment.verdict is Verdict.ALLOW
        assert assessment.findings == ()
        assert not assessment.requires_human
        assert assessment.blocked_reasons == ()
        assert assessment.escalation_reasons == ()

    def test_red_flag_without_evidence_escalates_and_flags_missing_evidence(self) -> None:
        case = make_case(
            symptoms=("crushing chest pain",), flags=CaseFlags(chest_pain=True)
        )
        assessment = SafetyPolicyEngine().evaluate(case)
        assert assessment.verdict is Verdict.ESCALATE
        assert assessment.requires_human
        assert "RF-001" in assessment.escalation_reasons
        assert "EVD-001" in assessment.escalation_reasons
        assert any(
            finding.severity is Severity.CRITICAL
            for finding in assessment.findings
        )

    def test_red_flag_with_evidence_does_not_flag_missing_evidence(self) -> None:
        case = make_case(
            symptoms=("chest pain",),
            evidence=(make_evidence(),),
            flags=CaseFlags(chest_pain=True),
        )
        rules = {finding.rule_id for finding in SafetyPolicyEngine().evaluate(case).findings}
        assert "RF-001" in rules
        assert "EVD-001" not in rules

    def test_allergy_conflict_blocks_even_with_red_flag(self) -> None:
        case = make_case(
            symptoms=("chest pain",),
            allergies=("penicillin",),
            medications=("amoxicillin",),
            evidence=(make_evidence(),),
        )
        assessment = SafetyPolicyEngine().evaluate(case)
        assert assessment.verdict is Verdict.BLOCK
        assert "ALG-001" in assessment.blocked_reasons
        assert "RF-001" in assessment.escalation_reasons
        assert assessment.requires_human

    @pytest.mark.parametrize(
        ("case", "rule_id"),
        [
            (make_case(flags=CaseFlags(polypharmacy=True)), "MED-001"),
            (
                make_case(
                    medications=("a", "b", "c", "d", "e"),
                ),
                "MED-001",
            ),
            (make_case(flags=CaseFlags(pediatric=True)), "PED-001"),
            (make_case(age=10), "PED-001"),
            (make_case(flags=CaseFlags(pregnancy=True)), "PRG-001"),
        ],
    )
    def test_escalation_rules(self, case: PatientCase, rule_id: str) -> None:
        assessment = SafetyPolicyEngine().evaluate(case)
        assert rule_id in assessment.escalation_reasons
        assert assessment.requires_human
        assert assessment.verdict is Verdict.ESCALATE

    def test_mental_health_flag_creates_red_flag_finding(self) -> None:
        case = make_case(flags=CaseFlags(mental_health_crisis=True))
        rules = [finding.rule_id for finding in SafetyPolicyEngine().evaluate(case).findings]
        assert "RF-003" in rules

    def test_shortness_of_breath_is_high_severity(self) -> None:
        case = make_case(symptoms=("shortness of breath",))
        finding = SafetyPolicyEngine().evaluate(case).findings[0]
        assert finding.severity is Severity.HIGH
        assert finding.rule_id == "RF-002"


# ---------------------------------------------------------------------------
# Hash-chained audit ledger
# ---------------------------------------------------------------------------


class TestAudit:
    def test_append_and_verify_chain(self) -> None:
        ledger = AuditLedger(clock=lambda: "2026-01-01T00:00:00+00:00")
        first = ledger.append("orchestrator", "case.received")
        second = ledger.append("router", "plan.created", {"roles": ["triage"]})
        assert first.index == 0
        assert first.prev_hash == GENESIS_HASH
        assert second.index == 1
        assert second.prev_hash == first.entry_hash
        assert len(ledger) == 2
        assert ledger.verify().valid
        assert ledger.verify_or_raise().valid

    def test_verify_reports_entry_digest_tamper(self) -> None:
        ledger = AuditLedger(clock=lambda: "t")
        ledger.append("a", "one", {"value": 1})
        ledger.append("b", "two", {"value": 2})
        object.__setattr__(ledger.entries[1], "details", {"value": 999})
        result = ledger.verify()
        assert not result.valid
        assert result.broken_index == 1
        assert result.reason == "entry digest mismatch"
        with pytest.raises(AuditIntegrityError, match="index 1"):
            ledger.verify_or_raise()

    def test_verify_reports_previous_hash_tamper(self) -> None:
        ledger = AuditLedger(clock=lambda: "t")
        ledger.append("a", "one")
        ledger.append("b", "two")
        object.__setattr__(ledger.entries[1], "prev_hash", "f" * 64)
        result = ledger.verify()
        assert not result.valid
        assert result.reason == "chain link mismatch"

    def test_verify_reports_index_tamper(self) -> None:
        ledger = AuditLedger(clock=lambda: "t")
        ledger.append("a", "one")
        ledger.append("b", "two")
        object.__setattr__(ledger.entries[1], "index", 7)
        result = ledger.verify()
        assert not result.valid
        assert result.reason == "chain link mismatch"

    def test_empty_chain_is_valid(self) -> None:
        result = AuditLedger().verify()
        assert result.valid
        assert result.broken_index is None
        assert result.reason == "chain intact"
        assert AuditLedger().entries == ()

    def test_digest_is_deterministic(self) -> None:
        args = (0, "t", "actor", "action", {"b": 2, "a": 1}, GENESIS_HASH)
        assert _digest(*args) == _digest(*args)
        assert len(_digest(*args)) == 64

    def test_changing_clock_changes_digest(self) -> None:
        first = AuditLedger(clock=lambda: "t1").append("a", "x")
        second = AuditLedger(clock=lambda: "t2").append("a", "x")
        assert first.entry_hash != second.entry_hash

    def test_utc_now_shape(self) -> None:
        value = utc_now()
        assert "T" in value
        assert value.endswith("+00:00")


# ---------------------------------------------------------------------------
# Deterministic agents
# ---------------------------------------------------------------------------


class TestAgents:
    def test_triage_critical(self) -> None:
        report = TriageAgent().assess(make_case(symptoms=("chest pain",)))
        assert report.acuity == "critical"
        assert report.red_flags == ("chest pain [RF-001]",)
        assert "mandatory" in report.rationale
        assert report.recommended_actions == (
            "Escalate immediately to emergency clinical review.",
            "Do not provide automated reassurance or self-care advice.",
        )

    def test_triage_urgent(self) -> None:
        report = TriageAgent().assess(make_case(symptoms=("shortness of breath",)))
        assert report.acuity == "urgent"
        assert "same-day" in report.recommended_actions[0]

    def test_triage_semi_urgent(self) -> None:
        report = TriageAgent().assess(
            make_case(symptoms=("fatigue", "nausea", "headache"))
        )
        assert report.acuity == "semi-urgent"
        assert "service window" in report.recommended_actions[0]

    def test_triage_routine(self) -> None:
        report = TriageAgent().assess(make_case())
        assert report.acuity == "routine"
        assert report.red_flags == ()
        assert "No red-flag terms" in report.rationale
        assert "routine" in report.recommended_actions[0].lower()

    def test_evidence_complete_match(self) -> None:
        bundle = EvidenceAgent().retrieve(
            make_case(
                symptoms=("fatigue",),
                evidence=(make_evidence(),),
            )
        )
        assert bundle.coverage == "complete"
        assert bundle.matched_ids == ("EV-T-1",)
        assert "matched the query" in bundle.note

    def test_evidence_default_query_uses_symptoms(self) -> None:
        bundle = EvidenceAgent().retrieve(
            make_case(symptoms=("fatigue", "dizziness"), evidence=(make_evidence(),))
        )
        assert bundle.query == "fatigue, dizziness"

    def test_evidence_query_override(self) -> None:
        bundle = EvidenceAgent().retrieve(
            make_case(symptoms=("fatigue",), evidence=(make_evidence(),)),
            query="unrelated words",
        )
        assert bundle.coverage == "fallback"
        assert bundle.matched_ids == ("EV-T-1",)
        assert "full synthetic bundle" in bundle.note

    def test_evidence_missing_when_no_bundle(self) -> None:
        bundle = EvidenceAgent().retrieve(make_case())
        assert bundle.coverage == "missing"
        assert bundle.matched_ids == ()
        assert "No synthetic evidence" in bundle.note

    def test_medication_conflict_recommendation(self) -> None:
        review = MedicationAgent().review(
            make_case(allergies=("penicillin",), medications=("amoxicillin",))
        )
        assert review.conflicts == ("penicillin allergy vs amoxicillin",)
        assert review.polypharmacy is False
        assert "Do not administer" in review.recommendation

    def test_medication_polypharmacy_recommendation(self) -> None:
        review = MedicationAgent().review(
            make_case(medications=("a", "b", "c", "d", "e"))
        )
        assert review.conflicts == ()
        assert review.polypharmacy
        assert "Polypharmacy" in review.recommendation

    def test_medication_clear_recommendation(self) -> None:
        review = MedicationAgent().review(make_case())
        assert review.conflicts == ()
        assert not review.polypharmacy
        assert "No rule-level allergy conflict" in review.recommendation

    def test_human_review_packet_with_findings(self) -> None:
        case = make_case(symptoms=("chest pain",))
        assessment = SafetyPolicyEngine().evaluate(case)
        request = HumanReviewAgent().request(case, assessment)
        assert "RF-001" in request.reason
        assert len(request.questions) == 3

    def test_human_review_packet_without_findings(self) -> None:
        assessment = SafetyPolicyEngine().evaluate(make_case())
        request = HumanReviewAgent().request(make_case(), assessment)
        assert request.reason == "Routine human confirmation requested for the synthetic case."

    def test_summarizer_full_context(self) -> None:
        case = demo_case()
        redaction = Redactor().redact(case.narrative)
        plan = AgentRouter().route(case)
        consent = ConsentGate().authorize_plan(plan, case.consent_scopes)
        assessment = SafetyPolicyEngine().evaluate(case)
        triage = TriageAgent().assess(case)
        evidence = EvidenceAgent().retrieve(case)
        medication = MedicationAgent().review(case)
        human = HumanReviewAgent().request(case, assessment)
        summary = SummarizerAgent().summarize(
            case, redaction, plan, consent, assessment, triage, evidence, medication, human
        )
        body = "\n".join(section.body for section in summary.sections)
        assert "Retrieval coverage" in body
        assert "Allergy conflicts" in body
        assert "Final verdict" in body
        assert "Reviewer packet" in body
        assert "EV-001" in [citation.identifier for citation in summary.citations]
        assert "RF-001" in [citation.identifier for citation in summary.citations]
        assert summary.citations[-1].kind == "policy"

    def test_summarizer_without_optional_agents(self) -> None:
        case = make_case()
        redaction = Redactor().redact(case.narrative)
        plan = AgentRouter().route(case)
        consent = ConsentGate().authorize_plan(plan, case.consent_scopes)
        assessment = SafetyPolicyEngine().evaluate(case)
        summary = SummarizerAgent().summarize(
            case,
            redaction,
            plan,
            consent,
            assessment,
            TriageAgent().assess(case),
        )
        body = "\n".join(section.body for section in summary.sections)
        assert "No evidence agent was routed" in body
        assert "No medication agent was routed" in body
        assert "No deterministic policy findings" in body
        assert "No human-review packet" in body
        assert summary.status == "allow"

    def test_summarizer_handles_unknown_evidence_id(self) -> None:
        case = make_case()
        redaction = Redactor().redact(case.narrative)
        plan = AgentRouter().route(case)
        consent = ConsentGate().authorize_plan(plan, case.consent_scopes)
        assessment = SafetyPolicyEngine().evaluate(case)
        summary = SummarizerAgent().summarize(
            case,
            redaction,
            plan,
            consent,
            assessment,
            TriageAgent().assess(case),
            evidence=EvidenceBundle("q", ("EV-UNKNOWN",), "complete", "note"),
        )
        assert summary.citations == ()

    def test_summarizer_reports_missing_human_packet_inconsistency(self) -> None:
        case = make_case(symptoms=("chest pain",))
        redaction = Redactor().redact(case.narrative)
        plan = AgentRouter().route(case)
        consent = ConsentGate().authorize_plan(plan, case.consent_scopes)
        assessment = SafetyPolicyEngine().evaluate(case)
        summary = SummarizerAgent().summarize(
            case,
            redaction,
            plan,
            consent,
            assessment,
            TriageAgent().assess(case),
        )
        body = "\n".join(section.body for section in summary.sections)
        assert "internal inconsistency" in body
        assert summary.status == "escalate — human review required"

    def test_disclaimers_are_explicit(self) -> None:
        assert any("not a medical device" in text for text in DISCLAIMERS)
        assert any("Synthetic" in text for text in DISCLAIMERS)


# ---------------------------------------------------------------------------
# Orchestrator end-to-end paths
# ---------------------------------------------------------------------------


class TestOrchestrator:
    def test_demo_case_escalates_with_full_audit(self) -> None:
        result = Orchestrator().run(demo_case())
        assert result.status is RunStatus.AWAITING_HUMAN_REVIEW
        assert result.requires_human
        assert result.policy.verdict is Verdict.ESCALATE
        assert result.audit.valid
        assert result.redaction.total >= 4
        assert "8891234" not in result.redacted_narrative
        assert "jane.synthetic@example.test" not in result.redacted_narrative
        assert "[[MRN_1]]" in result.redacted_narrative
        assert len(result.messages) == 5
        assert [message.kind for message in result.messages] == [
            MessageKind.TRIAGE_REPORT,
            MessageKind.EVIDENCE_BUNDLE,
            MessageKind.MEDICATION_REVIEW,
            MessageKind.HUMAN_REVIEW_REQUEST,
            MessageKind.SUMMARY_READY,
        ]
        identifiers = [citation.identifier for citation in result.summary.citations]
        assert "EV-001" in identifiers
        assert "RF-001" in identifiers
        assert "MED-001" in identifiers
        assert result.ledger[0].action == "case.received"
        assert result.ledger[-1].index == len(result.ledger) - 1

    def test_clean_case_completes_without_human(self) -> None:
        result = Orchestrator().run(make_case())
        assert result.status is RunStatus.COMPLETED
        assert not result.requires_human
        assert result.policy.verdict is Verdict.ALLOW
        assert result.audit.valid
        assert result.redaction.total == 0
        assert len(result.messages) == 2
        assert result.summary.citations == ()

    def test_allergy_conflict_blocks_safely(self) -> None:
        case = make_case(
            narrative="Synthetic case. MRN: 5556667.",
            allergies=("penicillin",),
            medications=("amoxicillin", "metformin"),
            evidence=(make_evidence(),),
        )
        result = Orchestrator().run(case)
        assert result.status is RunStatus.BLOCKED_SAFETY
        assert result.policy.verdict is Verdict.BLOCK
        assert result.messages == ()
        assert result.requires_human
        assert result.audit.valid
        assert "ALG-001" in result.summary.title or "Safety Block" in result.summary.title
        assert [citation.identifier for citation in result.summary.citations] == [
            "ALG-001"
        ]
        assert result.ledger[-1].action == "safety.blocked"

    def test_missing_consent_blocks_before_agents(self) -> None:
        scopes = ALL_SCOPES - {ConsentScope.MEDICATION_REVIEW}
        case = make_case(
            medications=("metformin", "lisinopril"),
            consent_scopes=frozenset(scopes),
        )
        result = Orchestrator().run(case)
        assert result.status is RunStatus.BLOCKED_CONSENT
        assert result.messages == ()
        assert result.requires_human
        assert not result.policy.findings
        assert result.audit.valid
        assert result.ledger[-1].action == "consent.denied"
        assert any(not decision.granted for decision in result.consent)
        assert result.summary.citations == ()

    def test_missing_triage_consent_denies(self) -> None:
        case = make_case(consent_scopes=frozenset())
        result = Orchestrator().run(case)
        assert result.status is RunStatus.BLOCKED_CONSENT
        denied_roles = {
            decision.role for decision in result.consent if not decision.granted
        }
        assert denied_roles == {AgentRole.TRIAGE, AgentRole.SUMMARIZER}

    def test_fixed_clock_makes_audit_deterministic(self) -> None:
        clock = lambda: "2026-01-01T00:00:00+00:00"  # noqa: E731
        result = Orchestrator(clock=clock).run(demo_case())
        assert {entry.timestamp for entry in result.ledger} == {
            "2026-01-01T00:00:00+00:00"
        }

    def test_injected_dependencies(self) -> None:
        orchestrator = Orchestrator(
            router=AgentRouter(),
            consent_gate=ConsentGate(),
            policy=SafetyPolicyEngine(),
            redactor=Redactor(),
        )
        result = orchestrator.run(make_case())
        assert result.status is RunStatus.COMPLETED

    def test_ph_i_in_narrative_is_redacted_everywhere(self) -> None:
        case = make_case(
            narrative=(
                "Synthetic contact jane@example.test, phone 555-123-4567, "
                "MRN: 1234567, on 2026-01-15."
            )
        )
        result = Orchestrator().run(case)
        assert result.redaction.total == 4
        assert "1234567" not in result.summary.render()
        assert "jane@example.test" not in result.summary.render()
        assert "[[EMAIL_1]]" in result.redacted_narrative

    def test_run_result_to_dict_is_json_serializable(self) -> None:
        result = Orchestrator().run(demo_case())
        payload = result.to_dict()
        encoded = json.dumps(payload)
        assert '"case_id": "SYN-1001"' in encoded
        assert payload["audit"]["verification"]["valid"] is True
        assert payload["policy"]["verdict"] == "escalate"
        assert payload["routing"][0]["role"] == "triage"
        assert payload["consent"][0]["granted"] is True
        assert payload["messages"][0]["kind"] == "triage_report"

    def test_ledger_links_are_consistent(self) -> None:
        result = Orchestrator().run(demo_case())
        assert result.ledger[0].prev_hash == GENESIS_HASH
        for previous, current in zip(result.ledger, result.ledger[1:]):
            assert current.prev_hash == previous.entry_hash
            assert current.index == previous.index + 1


# ---------------------------------------------------------------------------
# Case-file parsing and demo fixture
# ---------------------------------------------------------------------------


class TestCaseFile:
    def test_minimal_document(self) -> None:
        case = case_from_dict(
            {
                "case_id": "MIN-1",
                "narrative": "Synthetic narrative.",
                "age": 30,
            }
        )
        assert case.symptoms == ()
        assert case.consent_scopes == frozenset()
        assert case.flags == CaseFlags()
        assert case.evidence == ()

    def test_full_document(self) -> None:
        document = make_case_document(
            allergies=["penicillin"],
            flags={"chest_pain": True, "imaging_available": True},
            evidence=[
                {
                    "evidence_id": "EV-1",
                    "title": "Synthetic title",
                    "source": "fixture",
                    "text": "Synthetic text",
                    "kind": "checklist",
                },
                {
                    "evidence_id": "EV-2",
                    "title": "No kind",
                    "source": "fixture",
                    "text": "Defaults to guideline",
                },
            ],
        )
        case = case_from_dict(document)
        assert case.flags.chest_pain
        assert case.flags.imaging_available
        assert case.allergies == ("penicillin",)
        assert len(case.evidence) == 2
        assert case.evidence[1].kind == "guideline"
        assert len(case.consent_scopes) == len(ConsentScope)

    def test_non_mapping_document_rejected(self) -> None:
        with pytest.raises(CaseValidationError, match="JSON object"):
            case_from_dict(["not", "a", "mapping"])  # type: ignore[arg-type]

    def test_missing_required_fields(self) -> None:
        with pytest.raises(CaseValidationError, match="case_id"):
            case_from_dict({"narrative": "x", "age": 1})

    def test_invalid_age(self) -> None:
        with pytest.raises(CaseValidationError, match="integer"):
            case_from_dict({"case_id": "X", "narrative": "x", "age": "old"})

    def test_flags_must_be_mapping(self) -> None:
        with pytest.raises(CaseValidationError, match="flags"):
            case_from_dict(make_case_document(flags=["chest_pain"]))

    def test_unknown_flag_rejected(self) -> None:
        with pytest.raises(CaseValidationError, match="unknown case flag"):
            case_from_dict(make_case_document(flags={"chest_pain": True, "bogus": 1}))

    def test_unknown_consent_scope_rejected(self) -> None:
        with pytest.raises(CaseValidationError, match="unknown consent scope"):
            case_from_dict(make_case_document(consent=["care.triage", "bogus"]))

    def test_evidence_must_be_mapping(self) -> None:
        with pytest.raises(CaseValidationError, match="evidence item"):
            case_from_dict(make_case_document(evidence=["not-a-dict"]))

    def test_evidence_required_field_rejected(self) -> None:
        with pytest.raises(CaseValidationError, match="missing required field"):
            _evidence_from_mapping({"evidence_id": "EV-1"})

    def test_load_case_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "case.json"
        path.write_text(json.dumps(make_case_document()), encoding="utf-8")
        case = load_case(path)
        assert case.case_id == "SYN-FILE-1"

    def test_load_case_reports_bad_json(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(CaseValidationError, match="could not read"):
            load_case(path)

    def test_load_case_reports_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(CaseValidationError, match="could not read"):
            load_case(tmp_path / "absent.json")

    def test_demo_case_shape(self) -> None:
        case = demo_case()
        assert case.case_id == "SYN-1001"
        assert case.flags.chest_pain
        assert len(case.medications) >= 5
        assert len(case.consent_scopes) == len(ConsentScope)
        assert case.evidence[0].evidence_id == "EV-001"


# ---------------------------------------------------------------------------
# CLI behavior
# ---------------------------------------------------------------------------


class TestCLI:
    def test_help_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as excinfo:
            cli_module.main(["--help"])
        assert excinfo.value.code == 0
        assert "not a medical device" in capsys.readouterr().out

    def test_no_arguments_prints_help(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert cli_module.main([]) == 0
        assert "usage: ieesbots" in capsys.readouterr().out

    def test_demo_text_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert cli_module.main(["--demo"]) == 0
        output = capsys.readouterr().out
        assert "SYN-1001" in output
        assert "awaiting_human_review" in output
        assert "Audit chain: intact" in output
        assert "PHI tokens:" in output
        assert "Disclaimers" in output

    def test_demo_json_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert cli_module.main(["--demo", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["case_id"] == "SYN-1001"
        assert payload["status"] == "awaiting_human_review"
        assert payload["audit"]["verification"]["valid"] is True

    def test_case_file_text_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "case.json"
        path.write_text(json.dumps(make_case_document()), encoding="utf-8")
        assert cli_module.main(["--case", str(path)]) == 0
        output = capsys.readouterr().out
        assert "completed" in output
        assert "PHI tokens: 0" in output
        assert "(" not in output.split("PHI tokens: 0", 1)[1].splitlines()[0]

    def test_blocked_case_returns_nonzero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        document = make_case_document(
            allergies=["penicillin"],
            medications=["amoxicillin", "metformin"],
            symptoms=["fatigue"],
        )
        path = tmp_path / "blocked.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        assert cli_module.main(["--case", str(path)]) == 1
        assert "blocked_safety" in capsys.readouterr().out

    def test_missing_case_file_returns_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert cli_module.main(["--case", str(tmp_path / "absent.json")]) == 2
        assert "error:" in capsys.readouterr().err

    def test_invalid_json_returns_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "broken.json"
        path.write_text("{", encoding="utf-8")
        assert cli_module.main(["--case", str(path)]) == 2
        assert "could not read" in capsys.readouterr().err

    def test_invalid_schema_returns_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"case_id": "X"}), encoding="utf-8")
        assert cli_module.main(["--case", str(path)]) == 2
        assert "missing required field" in capsys.readouterr().err

    def test_render_result_broken_audit_label(self) -> None:
        result = Orchestrator().run(make_case())
        tampered = replace(
            result, audit=AuditVerification(False, 3, "chain link mismatch")
        )
        output = cli_module.render_result(tampered)
        assert "Audit chain: BROKEN at 3" in output

    def test_render_result_with_phi_counts(self) -> None:
        result = Orchestrator().run(demo_case())
        output = cli_module.render_result(result)
        assert "PHI tokens: 4" in output
        assert "mrn=1" in output
        assert "email=1" in output

    def test_module_entry_point_runs_demo(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["ieesbots", "--demo", "--json"])
        with pytest.raises(SystemExit) as excinfo:
            runpy.run_module("ieesbots", run_name="__main__")
        assert excinfo.value.code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["case_id"] == "SYN-1001"

    def test_main_module_can_be_imported(self) -> None:
        module = importlib.import_module("ieesbots.__main__")
        assert module.main is cli_module.main

    def test_parser_exposes_documented_flags(self) -> None:
        parser = cli_module.build_parser()
        args = parser.parse_args(["--demo", "--json"])
        assert args.demo and args.as_json
        case_args = parser.parse_args(["--case", "x.json"])
        assert case_args.case == "x.json"


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------


def test_public_exports_are_importable() -> None:
    import ieesbots

    assert ieesbots.__version__ == "1.0.0"
    assert ieesbots.__author__ == "Kyaw Kyaw Oo"
    for name in ieesbots.__all__:
        assert hasattr(ieesbots, name)


def test_run_result_type_is_exposed() -> None:
    result = Orchestrator().run(make_case())
    assert isinstance(result, RunResult)
    assert isinstance(result.summary, Summary)
    assert isinstance(result.policy, PolicyAssessment)
    assert isinstance(result.consent[0], ConsentDecision)
    assert isinstance(result.plan.decisions[0], RoutingDecision)
    assert isinstance(result.summary.sections[0], SummarySection)
    assert isinstance(result.messages[0], AgentMessage)
    assert isinstance(result.messages[0].payload, TriageReport)
    assert isinstance(result.summary.citations, tuple)
    assert result.summary.disclaimers == DISCLAIMERS


def test_redaction_result_alias_shape() -> None:
    result = RedactionResult("text", RedactionReport({}, 0))
    assert result.text == "text"
