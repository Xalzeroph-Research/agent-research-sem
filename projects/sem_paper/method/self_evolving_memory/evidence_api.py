from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Protocol

from research_platform.platform.kernel import JsonValue

from .json_snapshot import freeze_json


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    evidence_id: str
    sequence: int
    payload: JsonValue
    digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_id, str) or not self.evidence_id.strip():
            raise ValueError("J_mem evidence_id must be a non-empty string")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence <= 0:
            raise ValueError("J_mem evidence sequence must be a positive integer")
        object.__setattr__(
            self,
            "payload",
            freeze_json(self.payload, label="J_mem evidence payload"),
        )
        if not _is_sha256(self.digest):
            raise ValueError("J_mem evidence digest must be a lower-case SHA-256 digest")


@dataclass(frozen=True, slots=True)
class EvidenceCut:
    sequence: int
    count: int
    digest: str

    def __post_init__(self) -> None:
        for label, value in (("sequence", self.sequence), ("count", self.count)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"J_mem cut {label} must be a non-negative integer")
        if (self.count == 0) != (self.sequence == 0):
            raise ValueError("J_mem empty cut sequence/count are inconsistent")
        if not _is_sha256(self.digest):
            raise ValueError("J_mem cut digest must be a lower-case SHA-256 digest")


@dataclass(frozen=True, slots=True)
class EvidenceSnapshot:
    sequence: int
    rows: tuple[EvidenceRecord, ...]
    digest: str

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
            raise ValueError("J_mem snapshot sequence must be a non-negative integer")
        if not isinstance(self.rows, tuple):
            raise ValueError("J_mem snapshot rows must be a tuple")
        if any(not isinstance(row, EvidenceRecord) for row in self.rows):
            raise ValueError("J_mem snapshot rows must contain EvidenceRecord values")
        if self.rows:
            if self.sequence != self.rows[-1].sequence:
                raise ValueError("J_mem snapshot sequence must match its final evidence row")
            sequences = tuple(row.sequence for row in self.rows)
            if any(left >= right for left, right in zip(sequences, sequences[1:])):
                raise ValueError("J_mem snapshot sequences must increase")
            evidence_ids = tuple(row.evidence_id for row in self.rows)
            if len(evidence_ids) != len(set(evidence_ids)):
                raise ValueError("J_mem snapshot evidence ids must be unique")
        elif self.sequence != 0:
            raise ValueError("empty J_mem snapshot sequence must be zero")
        if not _is_sha256(self.digest):
            raise ValueError("J_mem snapshot digest must be a lower-case SHA-256 digest")


class EvidenceReadPort(Protocol):
    """Pinned canonical evidence read surface independent of physical storage/retrieval algorithm."""

    @property
    def sequence(self) -> int: ...

    @property
    def digest(self) -> str: ...

    @property
    def count(self) -> int: ...

    def latest(self) -> EvidenceRecord | None: ...
    def contains(self, evidence_id: str) -> bool: ...
    def get(self, evidence_id: str) -> EvidenceRecord | None: ...
    def sequence_of(self, evidence_id: str) -> int | None: ...
    def prefix_digest(self, count: int) -> str: ...
    def iter_rows(self, start_position: int = 0) -> Iterator[EvidenceRecord]: ...
    def materialize(self) -> EvidenceSnapshot: ...


class EvidenceMaterializationSource(Protocol):
    """Source that atomically pins one canonical evidence cut for materialization."""

    def pin(self) -> EvidenceReadPort: ...


class EvidenceStorePort(EvidenceMaterializationSource, Protocol):
    """Mutable canonical J_mem authority independent of physical storage."""

    def append_payload(self, evidence_id: str, sequence: int, payload: JsonValue) -> EvidenceRecord: ...
    def cut(self) -> EvidenceCut: ...
    def pin(self) -> EvidenceReadPort: ...
    def read_view(self) -> EvidenceReadPort: ...
    def snapshot(self) -> EvidenceSnapshot: ...
    def restore(self, snapshot: EvidenceSnapshot) -> None: ...


class EvidenceSnapshotPort(Protocol):
    """Minimal canonical snapshot source used by legacy flat materialization."""

    def snapshot(self) -> EvidenceSnapshot: ...


__all__ = [
    "EvidenceCut",
    "EvidenceMaterializationSource",
    "EvidenceReadPort",
    "EvidenceRecord",
    "EvidenceSnapshot",
    "EvidenceSnapshotPort",
    "EvidenceStorePort",
]
