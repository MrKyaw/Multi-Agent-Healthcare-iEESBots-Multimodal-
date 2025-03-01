"""Hash-chained audit ledger with tamper detection.

Each entry commits to the previous entry's digest, its own metadata, and a
canonical JSON encoding of its details.  Recomputing the chain therefore
detects edits, reordering, and broken links.  This is an educational,
single-process chain — not a distributed ledger and not a substitute for
append-only infrastructure.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from .exceptions import AuditIntegrityError
from .models import AuditEntry, AuditVerification

GENESIS_HASH = "0" * 64


def utc_now() -> str:
    """Return a stable, timezone-aware timestamp string."""

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _digest(
    index: int,
    timestamp: str,
    actor: str,
    action: str,
    details: Mapping[str, Any],
    prev_hash: str,
) -> str:
    """Compute the SHA-256 digest for one entry."""

    body = {
        "index": index,
        "timestamp": timestamp,
        "actor": actor,
        "action": action,
        "details": dict(details),
        "prev_hash": prev_hash,
    }
    canonical = json.dumps(
        body, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class AuditLedger:
    """Append-only-in-spirit in-memory audit chain."""

    def __init__(self, clock: Callable[[], str] | None = None) -> None:
        self._entries: list[AuditEntry] = []
        self._clock = clock if clock is not None else utc_now

    def append(
        self,
        actor: str,
        action: str,
        details: Mapping[str, Any] | None = None,
    ) -> AuditEntry:
        """Append one entry and return it.

        ``details`` must be JSON-serializable (non-serializable values are
        coerced with ``str`` when hashing, but should be avoided).
        """

        payload: Mapping[str, Any] = details if details is not None else {}
        index = len(self._entries)
        prev_hash = self._entries[-1].entry_hash if self._entries else GENESIS_HASH
        timestamp = self._clock()
        entry = AuditEntry(
            index=index,
            timestamp=timestamp,
            actor=actor,
            action=action,
            details=dict(payload),
            prev_hash=prev_hash,
            entry_hash=_digest(
                index=index,
                timestamp=timestamp,
                actor=actor,
                action=action,
                details=payload,
                prev_hash=prev_hash,
            ),
        )
        self._entries.append(entry)
        return entry

    def verify(self) -> AuditVerification:
        """Recompute the chain and report the first broken link, if any."""

        expected_prev = GENESIS_HASH
        expected_index = 0
        for entry in self._entries:
            if entry.index != expected_index or entry.prev_hash != expected_prev:
                return AuditVerification(
                    valid=False,
                    broken_index=entry.index,
                    reason="chain link mismatch",
                )
            recomputed = _digest(
                index=entry.index,
                timestamp=entry.timestamp,
                actor=entry.actor,
                action=entry.action,
                details=entry.details,
                prev_hash=entry.prev_hash,
            )
            if recomputed != entry.entry_hash:
                return AuditVerification(
                    valid=False,
                    broken_index=entry.index,
                    reason="entry digest mismatch",
                )
            expected_prev = entry.entry_hash
            expected_index += 1
        return AuditVerification(valid=True, broken_index=None, reason="chain intact")

    def verify_or_raise(self) -> AuditVerification:
        """Verify and raise :class:`AuditIntegrityError` on failure."""

        result = self.verify()
        if not result.valid:
            raise AuditIntegrityError(
                f"audit chain broken at index {result.broken_index}: {result.reason}"
            )
        return result

    @property
    def entries(self) -> tuple[AuditEntry, ...]:
        """Immutable snapshot of the chain."""

        return tuple(self._entries)

    def __len__(self) -> int:
        return len(self._entries)
