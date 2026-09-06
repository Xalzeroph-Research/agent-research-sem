from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from research_platform.platform.kernel import canonical_digest
from .evidence_api import EvidenceSnapshotPort


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


@dataclass(frozen=True, slots=True)
class MaterializationContract:
    node_id: str
    source_selector: object
    transform_plan: object

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str) or not self.node_id.strip():
            raise ValueError("materialization contract node_id must be a non-empty string")


class PreparedStatus(StrEnum):
    PREPARED = "prepared"
    COMMITTED = "committed"
    ABANDONED = "abandoned"


@dataclass(frozen=True, slots=True)
class PreparedGeneration:
    generation: str
    base_generation: str
    candidate_id: str
    source_sequence: int
    source_snapshot_digest: str
    target_spec_digest: str
    records: tuple[tuple[str, str], ...]
    status: PreparedStatus = PreparedStatus.PREPARED
    typed_generation: object | None = None

    def __post_init__(self) -> None:
        for label, value in (
            ("generation", self.generation),
            ("base_generation", self.base_generation),
            ("candidate_id", self.candidate_id),
            ("target_spec_digest", self.target_spec_digest),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"prepared generation {label} must be a non-empty string")
        if (
            isinstance(self.source_sequence, bool)
            or not isinstance(self.source_sequence, int)
            or self.source_sequence < 0
        ):
            raise ValueError("prepared generation source_sequence must be a non-negative integer")
        if not _is_sha256(self.source_snapshot_digest):
            raise ValueError("prepared generation source snapshot digest must be a lower-case SHA-256 digest")
        if not isinstance(self.records, tuple):
            raise ValueError("prepared generation records must be a tuple")
        for row in self.records:
            if (
                not isinstance(row, tuple)
                or len(row) != 2
                or any(not isinstance(value, str) or not value.strip() for value in row)
            ):
                raise ValueError("prepared generation records must contain non-empty string pairs")
        if not isinstance(self.status, PreparedStatus):
            raise ValueError("prepared generation status must be a PreparedStatus")
        if self.typed_generation is not None and getattr(self.typed_generation, "generation", None) != self.generation:
            raise ValueError("typed materialized generation identity does not match prepared generation")


class Materializer:
    """Clean-generation builder consuming only the canonical J_mem snapshot contract."""

    def __init__(self, evidence: EvidenceSnapshotPort) -> None:
        self.evidence = evidence

    def clean_build(
        self,
        generation: str,
        *,
        base_generation: str,
        candidate_id: str,
        target_spec_digest: str,
        contracts: tuple[MaterializationContract, ...],
        target_spec: object | None = None,
    ) -> PreparedGeneration:
        if len({contract.node_id for contract in contracts}) != len(contracts):
            raise ValueError("duplicate node materialization contract")
        cut = self.evidence.snapshot()
        records = tuple(
            (
                contract.node_id,
                f"materialized:{cut.sequence}:"
                f"{canonical_digest({'selector': contract.source_selector, 'transform': contract.transform_plan})[:16]}",
            )
            for contract in contracts
        )
        return PreparedGeneration(
            generation,
            base_generation,
            candidate_id,
            cut.sequence,
            cut.digest,
            target_spec_digest,
            records,
            typed_generation=None,
        )
