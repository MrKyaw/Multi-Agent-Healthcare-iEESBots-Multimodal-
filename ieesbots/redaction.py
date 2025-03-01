"""Regex-based PHI redaction with reversible, in-memory tokenization.

The redactor is designed for deterministic tests and offline demos.  It removes
common identifiers from free text, replaces each unique value with a stable
token, and keeps the token-to-value mapping in a local vault that never touches
disk.  This is **not** a complete de-identification system and must not be
treated as HIPAA compliance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Pattern

from .models import RedactionReport


class PHIKind(str, Enum):
    """Identifier categories recognized by the default rule set."""

    MRN = "mrn"
    SSN = "ssn"
    PHONE = "phone"
    EMAIL = "email"
    DATE = "date"


#: Ordered rules.  More specific labeled identifiers run before generic ones.
DEFAULT_PATTERNS: tuple[tuple[PHIKind, Pattern[str]], ...] = (
    (PHIKind.EMAIL, re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", re.IGNORECASE)),
    (
        PHIKind.MRN,
        re.compile(r"\bMRN\s*(?:[:#-]\s*)?\d{6,10}\b", re.IGNORECASE),
    ),
    (PHIKind.SSN, re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    (
        PHIKind.PHONE,
        re.compile(
            r"(?<!\w)(?:\+1[-. ]?)?(?:\(\d{3}\)|\d{3})[-. ]?\d{3}[-. ]?\d{4}\b"
        ),
    ),
    (
        PHIKind.DATE,
        re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{4}\b"),
    ),
)

TOKEN_PATTERN = re.compile(r"\[\[([A-Z]+)_(\d+)\]\]")


class PhiVault:
    """Local, in-memory, reversible token store.

    The vault is process-local by design: discarding it makes redaction
    irreversible.  Tests use it to prove round-trip behavior; production-like
    use should persist the mapping only in an approved secrets system.
    """

    def __init__(self) -> None:
        self._by_value: dict[tuple[str, str], str] = {}
        self._by_token: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    def store(self, kind: PHIKind, value: str) -> str:
        """Return a stable token for ``value``, allocating one if necessary."""

        key = (kind.value, value)
        existing = self._by_value.get(key)
        if existing is not None:
            return existing
        counter = self._counters.get(kind.value, 0) + 1
        self._counters[kind.value] = counter
        token = f"[[{kind.value.upper()}_{counter}]]"
        self._by_value[key] = token
        self._by_token[token] = value
        return token

    def resolve(self, token: str) -> str | None:
        """Return the original value for a token, or ``None`` if unknown."""

        return self._by_token.get(token)

    def tokens(self) -> tuple[str, ...]:
        """Return all allocated tokens in insertion order."""

        return tuple(self._by_token)

    def __len__(self) -> int:
        return len(self._by_token)


@dataclass(frozen=True)
class RedactionResult:
    """Redacted text plus a category-level report."""

    text: str
    report: RedactionReport


class Redactor:
    """Apply the default PHI rules and manage a local token vault."""

    def __init__(
        self,
        vault: PhiVault | None = None,
        patterns: tuple[tuple[PHIKind, Pattern[str]], ...] = DEFAULT_PATTERNS,
    ) -> None:
        self.vault = vault if vault is not None else PhiVault()
        self._patterns = patterns

    def redact(self, text: str) -> RedactionResult:
        """Redact all recognized identifiers in ``text``.

        Repeated values receive the same token, so a narrative and a later
        evidence snippet can be joined without re-identifying the patient.
        """

        counts: dict[str, int] = {}
        redacted = text
        for kind, pattern in self._patterns:

            def replace(match: re.Match[str], kind: PHIKind = kind) -> str:
                counts[kind.value] = counts.get(kind.value, 0) + 1
                return self.vault.store(kind, match.group(0))

            redacted = pattern.sub(replace, redacted)
        report = RedactionReport(
            counts=dict(counts),
            total=sum(counts.values()),
        )
        return RedactionResult(text=redacted, report=report)

    def detokenize(self, text: str) -> str:
        """Reverse known tokens; unknown tokens are left untouched."""

        return TOKEN_PATTERN.sub(
            lambda match: self.vault.resolve(match.group(0)) or match.group(0),
            text,
        )

    def report_counts(self) -> Mapping[str, int]:
        """Return per-kind counts accumulated by the vault's patterns."""

        counts: dict[str, int] = {}
        for token in self.vault.tokens():
            kind = token[2:].split("_", 1)[0].lower()
            counts[kind] = counts.get(kind, 0) + 1
        return counts
