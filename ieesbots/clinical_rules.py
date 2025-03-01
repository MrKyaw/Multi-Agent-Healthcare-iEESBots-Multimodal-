"""Deterministic clinical-safety primitives shared by agents and policy.

These rules are intentionally conservative, transparent, and small.  They are
*safety scaffolding for a synthetic research prototype*, not validated clinical
decision support.  Every rule is a blunt keyword or table lookup that a reviewer
can audit in seconds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .models import PatientCase, Severity

#: Red-flag terms mapped to a stable rule id and severity.  Order is preserved
#: so reports and audit entries are reproducible.
RED_FLAG_TERMS: Mapping[str, tuple[str, Severity]] = {
    "chest pain": ("RF-001", Severity.CRITICAL),
    "shortness of breath": ("RF-002", Severity.HIGH),
    "suicidal": ("RF-003", Severity.CRITICAL),
    "stroke": ("RF-004", Severity.CRITICAL),
    "severe bleeding": ("RF-005", Severity.CRITICAL),
}

#: Small medication-family table used to detect allergy conflicts without a
#: drug database.  It is illustrative, not exhaustive.
ALLERGY_FAMILIES: Mapping[str, frozenset[str]] = {
    "penicillin": frozenset(
        {"penicillin", "amoxicillin", "ampicillin", "augmentin", "piperacillin"}
    ),
    "sulfa": frozenset(
        {"sulfa", "sulfamethoxazole", "trimethoprim-sulfamethoxazole", "bactrim"}
    ),
    "nsaid": frozenset({"nsaid", "ibuprofen", "naproxen", "aspirin", "diclofenac"}),
    "cephalosporin": frozenset({"cephalosporin", "cephalexin", "ceftriaxone"}),
}


@dataclass(frozen=True)
class RedFlagMatch:
    """A red-flag term found in a case, with its governing policy rule."""

    term: str
    rule_id: str
    severity: Severity


def matching_red_flags(case: PatientCase) -> tuple[RedFlagMatch, ...]:
    """Return every red flag present in symptoms or structured flags.

    Structured flags are converted into synthetic symptom terms so that a case
    with ``chest_pain=True`` behaves identically to one whose symptom list says
    "chest pain".
    """

    text = " ".join(case.symptoms).lower()
    if case.flags.chest_pain:
        text = f"{text} chest pain"
    if case.flags.mental_health_crisis:
        text = f"{text} suicidal ideation"
    matches = []
    for term, (rule_id, severity) in RED_FLAG_TERMS.items():
        if term in text:
            matches.append(RedFlagMatch(term=term, rule_id=rule_id, severity=severity))
    return tuple(matches)


def _same_family(allergy: str, medication: str) -> bool:
    """Return whether two normalized names share an allergy family."""

    for family in ALLERGY_FAMILIES.values():
        if allergy in family and medication in family:
            return True
    return False


def allergy_conflicts(case: PatientCase) -> tuple[tuple[str, str], ...]:
    """Return ``(allergy, medication)`` pairs that look unsafe.

    Matching is intentionally over-inclusive: exact containment or membership in
    the same illustrative drug family is enough to block the case and ask a
    human to resolve it.
    """

    allergies = {item.strip().lower() for item in case.allergies if item.strip()}
    medications = {item.strip().lower() for item in case.medications if item.strip()}
    conflicts = []
    for allergy in sorted(allergies):
        for medication in sorted(medications):
            if (
                allergy in medication
                or medication in allergy
                or _same_family(allergy, medication)
            ):
                conflicts.append((allergy, medication))
    return tuple(conflicts)


def is_polypharmacy(case: PatientCase) -> bool:
    """Return whether the case crosses the synthetic polypharmacy threshold."""

    return case.flags.polypharmacy or len(case.medications) >= 5
