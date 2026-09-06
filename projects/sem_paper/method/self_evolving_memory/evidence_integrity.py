from __future__ import annotations

import hashlib

from research_platform.platform.kernel import JsonValue, canonical_bytes

from .evidence_api import EvidenceRecord, EvidenceSnapshot


EMPTY_EVIDENCE_CHAIN_DIGEST = hashlib.sha256().hexdigest()


def build_evidence_record(evidence_id: str, sequence: int, payload: JsonValue) -> EvidenceRecord:
    """Build one canonical J_mem record without binding callers to a storage backend."""
    encoded = canonical_bytes(payload)
    return EvidenceRecord(evidence_id, sequence, payload, hashlib.sha256(encoded).hexdigest())


def evidence_chain_bytes(row: EvidenceRecord, *, first: bool) -> bytes:
    prefix = b"" if first else b"\n"
    return prefix + f"{row.sequence}:{row.evidence_id}:{row.digest}".encode("utf-8")


def validate_evidence_snapshot(snapshot: EvidenceSnapshot) -> None:
    """Validate one canonical J_mem cut without mutating a storage backend."""
    if isinstance(snapshot.sequence, bool) or not isinstance(snapshot.sequence, int) or snapshot.sequence < 0:
        raise ValueError("J_mem snapshot sequence must be a non-negative integer")
    if not isinstance(snapshot.digest, str) or len(snapshot.digest) != 64 or any(
        char not in "0123456789abcdef" for char in snapshot.digest
    ):
        raise ValueError("J_mem snapshot digest must be a lower-case SHA-256 digest")
    hasher = hashlib.sha256()
    seen_ids: set[str] = set()
    previous_sequence = 0
    for position, row in enumerate(snapshot.rows):
        if not isinstance(row.evidence_id, str) or not row.evidence_id.strip():
            raise ValueError("J_mem evidence_id must be non-empty")
        if isinstance(row.sequence, bool) or not isinstance(row.sequence, int) or row.sequence <= previous_sequence:
            raise ValueError("J_mem sequence must increase")
        if row.evidence_id in seen_ids:
            raise ValueError("duplicate J_mem evidence_id")
        expected = build_evidence_record(row.evidence_id, row.sequence, row.payload).digest
        if row.digest != expected:
            raise ValueError("J_mem evidence digest mismatch")
        hasher.update(evidence_chain_bytes(row, first=position == 0))
        seen_ids.add(row.evidence_id)
        previous_sequence = row.sequence
    expected_sequence = previous_sequence if snapshot.rows else 0
    if snapshot.sequence != expected_sequence or snapshot.digest != hasher.hexdigest():
        raise ValueError("J_mem snapshot sequence/digest mismatch")


__all__ = [
    "EMPTY_EVIDENCE_CHAIN_DIGEST",
    "build_evidence_record",
    "evidence_chain_bytes",
    "validate_evidence_snapshot",
]
