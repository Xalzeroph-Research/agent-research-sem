from __future__ import annotations

from research_platform.data.state.api import AggregateValue, AtomicMutation
from research_platform.platform.kernel import canonical_digest

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from .materialization import PreparedGeneration, PreparedStatus


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


class AdoptionPreparationStage(StrEnum):
    PROOF = "proof"
    BASE_STATE = "base_state"
    GENERATION = "generation"
    MATERIALIZATION = "materialization"
    MUTATION_COMPILE = "mutation_compile"


class AdoptionPreparationError(RuntimeError):
    def __init__(self, stage: AdoptionPreparationStage, code: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage
        self.code = code


@dataclass(frozen=True, slots=True)
class EvolutionLedgerEntry:
    candidate_id: str
    base_generation: str
    adopted_generation: str
    evaluation_pair_id: str
    target_spec_digest: str
    source_snapshot_digest: str
    source_sequence: int

    _DOCUMENT_FIELDS: ClassVar[frozenset[str]] = frozenset({
        "candidate_id",
        "base_generation",
        "adopted_generation",
        "evaluation_pair_id",
        "target_spec_digest",
        "source_snapshot_digest",
        "source_sequence",
    })

    def __post_init__(self) -> None:
        for label, value in (
            ("candidate_id", self.candidate_id),
            ("base_generation", self.base_generation),
            ("adopted_generation", self.adopted_generation),
            ("evaluation_pair_id", self.evaluation_pair_id),
            ("target_spec_digest", self.target_spec_digest),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"evolution ledger {label} must be a non-empty string")
        if not _is_sha256(self.source_snapshot_digest):
            raise ValueError("evolution ledger source snapshot digest must be a lower-case SHA-256 digest")
        if isinstance(self.source_sequence, bool) or not isinstance(self.source_sequence, int) or self.source_sequence < 0:
            raise ValueError("evolution ledger source_sequence must be a non-negative integer")

    def to_document(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "base_generation": self.base_generation,
            "adopted_generation": self.adopted_generation,
            "evaluation_pair_id": self.evaluation_pair_id,
            "target_spec_digest": self.target_spec_digest,
            "source_snapshot_digest": self.source_snapshot_digest,
            "source_sequence": self.source_sequence,
        }

    @classmethod
    def from_document(cls, value: object) -> "EvolutionLedgerEntry":
        if not isinstance(value, dict) or set(value) != cls._DOCUMENT_FIELDS:
            raise ValueError("evolution ledger document schema mismatch")
        text_fields = (
            "candidate_id",
            "base_generation",
            "adopted_generation",
            "evaluation_pair_id",
            "target_spec_digest",
            "source_snapshot_digest",
        )
        if any(not isinstance(value[name], str) for name in text_fields):
            raise ValueError("evolution ledger document text field is invalid")
        sequence = value["source_sequence"]
        if isinstance(sequence, bool) or not isinstance(sequence, int):
            raise ValueError("evolution ledger document source_sequence is invalid")
        return cls(
            candidate_id=value["candidate_id"],
            base_generation=value["base_generation"],
            adopted_generation=value["adopted_generation"],
            evaluation_pair_id=value["evaluation_pair_id"],
            target_spec_digest=value["target_spec_digest"],
            source_snapshot_digest=value["source_snapshot_digest"],
            source_sequence=sequence,
        )


@dataclass(frozen=True, slots=True)
class PreparedAdoption:
    generation: str
    prepared_generation: PreparedGeneration
    architecture_mutation: AtomicMutation
    ledger_mutation: AtomicMutation
    ledger_entry: EvolutionLedgerEntry

    def __post_init__(self) -> None:
        if not isinstance(self.generation, str) or not self.generation.strip():
            raise ValueError("prepared adoption generation must be a non-empty string")
        if not isinstance(self.prepared_generation, PreparedGeneration):
            raise ValueError("prepared adoption materialization is invalid")
        if not isinstance(self.architecture_mutation, AtomicMutation) or not isinstance(self.ledger_mutation, AtomicMutation):
            raise ValueError("prepared adoption mutations must be AtomicMutation values")
        if not isinstance(self.ledger_entry, EvolutionLedgerEntry):
            raise ValueError("prepared adoption ledger entry is invalid")
        self._validate_identity_cut()
        self._validate_mutations()
        self._validate_payload_bindings()

    def _validate_identity_cut(self) -> None:
        prepared = self.prepared_generation
        if prepared.status is not PreparedStatus.PREPARED:
            raise ValueError("prepared adoption requires a PREPARED materialization")
        if any(value != self.generation for value in (
            prepared.generation,
            self.architecture_mutation.new_generation,
            self.ledger_mutation.new_generation,
            self.ledger_entry.adopted_generation,
        )):
            raise ValueError("prepared adoption generation identities do not match")
        if self.ledger_entry.candidate_id != prepared.candidate_id:
            raise ValueError("prepared adoption candidate identity does not match ledger entry")
        if self.ledger_entry.base_generation != prepared.base_generation:
            raise ValueError("prepared adoption base generation does not match ledger entry")
        if self.ledger_entry.target_spec_digest != prepared.target_spec_digest:
            raise ValueError("prepared adoption target spec digest does not match ledger entry")
        if (
            self.ledger_entry.source_sequence != prepared.source_sequence
            or self.ledger_entry.source_snapshot_digest != prepared.source_snapshot_digest
        ):
            raise ValueError("prepared adoption source cut does not match ledger entry")

    def _validate_mutations(self) -> None:
        prepared = self.prepared_generation
        if self.architecture_mutation.aggregate_id == self.ledger_mutation.aggregate_id:
            raise ValueError("prepared adoption authoritative aggregate ids must be distinct")
        if any(mutation.expected_generation != prepared.base_generation for mutation in (
            self.architecture_mutation,
            self.ledger_mutation,
        )):
            raise ValueError("prepared adoption mutation base generation mismatch")
        for label, mutation in (
            ("architecture", self.architecture_mutation),
            ("ledger", self.ledger_mutation),
        ):
            if canonical_digest(mutation.new_payload) != mutation.new_digest:
                raise ValueError(f"prepared adoption {label} mutation digest mismatch")

    def _validate_payload_bindings(self) -> None:
        prepared = self.prepared_generation
        architecture_payload = self.architecture_mutation.new_payload
        if not isinstance(architecture_payload, dict):
            raise ValueError("prepared adoption architecture payload must be an object")
        if (
            architecture_payload.get("source_sequence") != prepared.source_sequence
            or architecture_payload.get("source_snapshot_digest") != prepared.source_snapshot_digest
            or architecture_payload.get("materialized_records") != prepared.records
        ):
            raise ValueError("prepared adoption architecture payload does not match materialization cut")
        ledger_payload = self.ledger_mutation.new_payload
        if not isinstance(ledger_payload, list) or not ledger_payload:
            raise ValueError("prepared adoption ledger payload must contain the adopted entry")
        if ledger_payload[-1] != self.ledger_entry.to_document():
            raise ValueError("prepared adoption ledger tail does not match adopted entry")


@dataclass(frozen=True, slots=True)
class AdoptionBaseState:
    architecture: AggregateValue
    ledger: AggregateValue

    def __post_init__(self) -> None:
        if not isinstance(self.architecture, AggregateValue) or not isinstance(self.ledger, AggregateValue):
            raise ValueError("adoption base state requires typed aggregate values")
        if self.architecture.generation != self.ledger.generation:
            raise ValueError("adoption base architecture/ledger generations must match")


@dataclass(frozen=True, slots=True)
class MaterializedCandidate:
    generation: str
    prepared_generation: PreparedGeneration

    def __post_init__(self) -> None:
        if not isinstance(self.generation, str) or not self.generation.strip():
            raise ValueError("materialized candidate generation must be a non-empty string")
        if not isinstance(self.prepared_generation, PreparedGeneration):
            raise ValueError("materialized candidate prepared generation is invalid")
        if self.prepared_generation.generation != self.generation:
            raise ValueError("materialized candidate generation identity mismatch")
        if self.prepared_generation.status is not PreparedStatus.PREPARED:
            raise ValueError("materialized candidate requires a PREPARED generation")
