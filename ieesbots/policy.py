"""Clinical safety policy engine with block / escalate / allow verdicts.

The engine composes small deterministic rules.  Its precedence table is:

1. any ``BLOCK`` finding  -> final verdict ``BLOCK`` (no clinical guidance)
2. else any ``ESCALATE`` -> final verdict ``ESCALATE`` (human review required)
3. otherwise             -> ``ALLOW``

Every non-allow finding requires a licensed human reviewer.  Findings are
returned in rule-evaluation order and carry stable rule IDs for citation and
audit.
"""

from __future__ import annotations

from .clinical_rules import allergy_conflicts, is_polypharmacy, matching_red_flags
from .models import (
    PatientCase,
    PolicyAssessment,
    PolicyFinding,
    Severity,
    Verdict,
)


class SafetyPolicyEngine:
    """Evaluate high-risk rules against one synthetic case."""

    def evaluate(self, case: PatientCase) -> PolicyAssessment:
        """Return all findings plus the aggregate verdict and review flag."""

        red_flags = matching_red_flags(case)
        findings = []
        for match in red_flags:
            findings.append(
                PolicyFinding(
                    rule_id=match.rule_id,
                    category="red_flag",
                    severity=match.severity,
                    verdict=Verdict.ESCALATE,
                    rationale=(
                        f"Red-flag term '{match.term}' requires clinician "
                        "assessment before any automated guidance."
                    ),
                )
            )

        conflicts = allergy_conflicts(case)
        if conflicts:
            pairs = ", ".join(
                f"{allergy} -> {medication}" for allergy, medication in conflicts
            )
            findings.append(
                PolicyFinding(
                    rule_id="ALG-001",
                    category="allergy",
                    severity=Severity.CRITICAL,
                    verdict=Verdict.BLOCK,
                    rationale=(
                        "Potential allergy/medication conflict detected "
                        f"({pairs}); automated medication guidance is blocked."
                    ),
                )
            )

        if red_flags and not case.evidence:
            findings.append(
                PolicyFinding(
                    rule_id="EVD-001",
                    category="missing_evidence",
                    severity=Severity.HIGH,
                    verdict=Verdict.ESCALATE,
                    rationale=(
                        "The case contains a red flag but no synthetic evidence "
                        "bundle was supplied for grounding."
                    ),
                )
            )

        if is_polypharmacy(case):
            findings.append(
                PolicyFinding(
                    rule_id="MED-001",
                    category="polypharmacy",
                    severity=Severity.HIGH,
                    verdict=Verdict.ESCALATE,
                    rationale=(
                        "Five or more medications (or a polypharmacy flag) require "
                        "pharmacist review."
                    ),
                )
            )

        if case.flags.pediatric or case.age < 18:
            findings.append(
                PolicyFinding(
                    rule_id="PED-001",
                    category="pediatric",
                    severity=Severity.MODERATE,
                    verdict=Verdict.ESCALATE,
                    rationale=(
                        "Pediatric dosing and triage differ from adult care; "
                        "human pediatric review is required."
                    ),
                )
            )

        if case.flags.pregnancy:
            findings.append(
                PolicyFinding(
                    rule_id="PRG-001",
                    category="pregnancy",
                    severity=Severity.HIGH,
                    verdict=Verdict.ESCALATE,
                    rationale=(
                        "Pregnancy may change imaging and medication safety; "
                        "human review is required."
                    ),
                )
            )

        verdict = Verdict.ALLOW
        if any(finding.verdict is Verdict.BLOCK for finding in findings):
            verdict = Verdict.BLOCK
        elif any(finding.verdict is Verdict.ESCALATE for finding in findings):
            verdict = Verdict.ESCALATE

        requires_human = any(finding.requires_human for finding in findings)
        return PolicyAssessment(
            findings=tuple(findings),
            verdict=verdict,
            requires_human=requires_human,
        )
