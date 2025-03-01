"""Case loading and the built-in synthetic demo case.

The JSON schema is intentionally boring: a caller can construct a case by hand,
and every field is validated before the orchestrator runs.  The demo uses
fictional identifiers so redaction can be demonstrated safely.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .exceptions import CaseValidationError
from .models import (
    CaseFlags,
    ConsentScope,
    EvidenceItem,
    PatientCase,
)

_REQUIRED_CASE_FIELDS = ("case_id", "narrative", "age")
_REQUIRED_EVIDENCE_FIELDS = ("evidence_id", "title", "source", "text")


def _evidence_from_mapping(raw: Mapping[str, Any]) -> EvidenceItem:
    missing = [field for field in _REQUIRED_EVIDENCE_FIELDS if field not in raw]
    if missing:
        raise CaseValidationError(
            "evidence item is missing required field(s): " + ", ".join(missing)
        )
    return EvidenceItem(
        evidence_id=str(raw["evidence_id"]),
        title=str(raw["title"]),
        source=str(raw["source"]),
        text=str(raw["text"]),
        kind=str(raw.get("kind", "guideline")),
    )


def case_from_dict(data: Mapping[str, Any]) -> PatientCase:
    """Build a :class:`PatientCase` from a JSON-like mapping.

    Raises:
        CaseValidationError: if required fields, flags, scopes, or evidence
            items are missing or malformed.
    """

    if not isinstance(data, Mapping):
        raise CaseValidationError("case document must be a JSON object")
    missing = [field for field in _REQUIRED_CASE_FIELDS if field not in data]
    if missing:
        raise CaseValidationError(
            "case is missing required field(s): " + ", ".join(missing)
        )

    try:
        age = int(data["age"])
    except (TypeError, ValueError) as exc:
        raise CaseValidationError(f"age must be an integer, got {data['age']!r}") from exc

    flags_raw = data.get("flags", {})
    if not isinstance(flags_raw, Mapping):
        raise CaseValidationError("flags must be a JSON object")
    allowed_flags = set(CaseFlags.__dataclass_fields__)
    unknown_flags = set(flags_raw) - allowed_flags
    if unknown_flags:
        raise CaseValidationError(
            "unknown case flag(s): " + ", ".join(sorted(unknown_flags))
        )
    flags = CaseFlags(**{key: bool(value) for key, value in flags_raw.items()})

    scopes: set[ConsentScope] = set()
    for raw_scope in data.get("consent", ()):
        try:
            scopes.add(ConsentScope(raw_scope))
        except ValueError as exc:
            raise CaseValidationError(f"unknown consent scope: {raw_scope!r}") from exc

    evidence = []
    for raw_item in data.get("evidence", ()):
        if not isinstance(raw_item, Mapping):
            raise CaseValidationError("each evidence item must be a JSON object")
        evidence.append(_evidence_from_mapping(raw_item))

    return PatientCase(
        case_id=str(data["case_id"]),
        narrative=str(data["narrative"]),
        age=age,
        symptoms=tuple(str(item) for item in data.get("symptoms", ())),
        medications=tuple(str(item) for item in data.get("medications", ())),
        allergies=tuple(str(item) for item in data.get("allergies", ())),
        evidence=tuple(evidence),
        flags=flags,
        consent_scopes=frozenset(scopes),
    )


def load_case(path: str | Path) -> PatientCase:
    """Read and validate a synthetic case JSON file."""

    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaseValidationError(f"could not read case file: {exc}") from exc
    return case_from_dict(document)


def demo_case() -> PatientCase:
    """Return the built-in synthetic, high-acuity demo case.

    The case deliberately exercises every major control: PHI redaction, evidence
    retrieval, polypharmacy review, red-flag escalation, and human review.
    """

    return PatientCase(
        case_id="SYN-1001",
        narrative=(
            "Synthetic patient reports crushing chest pain and shortness of breath "
            "since this morning. MRN: 8891234. Contact (555) 010-2030 or "
            "jane.synthetic@example.test. Prior note dated 2026-01-15. "
            "All identifiers and clinical details are fictional."
        ),
        age=67,
        symptoms=("chest pain", "shortness of breath", "fatigue"),
        medications=(
            "atorvastatin",
            "metoprolol",
            "aspirin",
            "lisinopril",
            "metformin",
        ),
        allergies=("shellfish",),
        evidence=(
            EvidenceItem(
                evidence_id="EV-001",
                title="Synthetic chest pain triage checklist",
                source="Fictional clinical governance fixture (not a guideline)",
                text=(
                    "Synthetic checklist: chest pain with shortness of breath "
                    "requires immediate clinician assessment and an ECG. Automated "
                    "self-care advice must not be issued."
                ),
                kind="checklist",
            ),
            EvidenceItem(
                evidence_id="EV-002",
                title="Synthetic polypharmacy reconciliation checklist",
                source="Fictional clinical governance fixture (not a guideline)",
                text=(
                    "Synthetic checklist: five or more medications require a "
                    "pharmacist-led reconciliation before changes are suggested."
                ),
                kind="checklist",
            ),
        ),
        flags=CaseFlags(
            chest_pain=True,
            polypharmacy=True,
            imaging_available=True,
        ),
        consent_scopes=frozenset(ConsentScope),
    )
