from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from .architecture import MemoryArchitectureSpec, TransformPlan
from .architecture.records import NodePartitionedRecord
from .architecture.validation import ArchitectureValidator
from .evidence_api import EvidenceMaterializationSource, EvidenceReadPort
from .materialization import MaterializationContract, PreparedGeneration
from .typed_materialization_errors import TypedMaterializationError
from .typed_materialization_generation import TypedMaterializedGeneration
from .typed_materialization_validation import validate_materialized_records


class TypedNodeBuilderPort(Protocol):
    """Semantic transform seam; no default or lossy fallback is provided."""

    def build_records(
        self,
        architecture: MemoryArchitectureSpec,
        evidence: EvidenceReadPort,
        contracts: tuple[MaterializationContract, ...],
    ) -> Iterable[NodePartitionedRecord]: ...


@dataclass(frozen=True, slots=True)
class PinnedEvidenceMaterializationSource(EvidenceMaterializationSource):
    """Read-only materialization source over one already-pinned evidence cut."""

    evidence: EvidenceReadPort

    def pin(self) -> EvidenceReadPort:
        return self.evidence


class TypedMaterializerAdapter:
    """Adapter from typed materialization into the existing adoption prepare port."""

    def __init__(self, materializer: "TypedMemoryMaterializer") -> None:
        self.materializer = materializer

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
        if not isinstance(target_spec, MemoryArchitectureSpec):
            raise TypedMaterializationError("Deluxe adoption requires a typed MemoryArchitectureSpec target")
        typed = self.materializer.build(
            generation,
            base_generation=base_generation,
            candidate_id=candidate_id,
            architecture=target_spec,
            contracts=contracts,
        )
        records = tuple((record.node_id, record.record_id) for record in typed.records)
        return PreparedGeneration(
            generation,
            base_generation,
            candidate_id,
            typed.source_sequence,
            typed.source_snapshot_digest,
            target_spec_digest,
            records,
            typed_generation=typed,
        )


class TypedMemoryMaterializer:
    """Build an immutable node-partitioned generation from J_mem only.

    The injected builder performs the semantic node transforms. This class
    refuses to infer a typed payload from an arbitrary evidence row and never
    reuses the legacy flat `(node_id, string)` placeholder path.
    """

    def __init__(self, evidence: EvidenceMaterializationSource, builder: TypedNodeBuilderPort) -> None:
        if not callable(getattr(builder, "build_records", None)):
            raise TypedMaterializationError("typed materializer requires an explicit node builder")
        self.evidence = evidence
        self.builder = builder
        self.validator = ArchitectureValidator()

    def build(
        self,
        generation: str,
        *,
        base_generation: str,
        candidate_id: str,
        architecture: MemoryArchitectureSpec,
        contracts: tuple[MaterializationContract, ...],
    ) -> TypedMaterializedGeneration:
        self.validator.verify(architecture)
        if not generation.strip() or not base_generation.strip() or not candidate_id.strip():
            raise TypedMaterializationError("typed materialization identity is required")
        node_ids = {node.node_id for node in architecture.nodes}
        contract_ids = tuple(contract.node_id for contract in contracts)
        if len(contract_ids) != len(set(contract_ids)):
            raise TypedMaterializationError("duplicate typed materialization contract")
        if set(contract_ids) != node_ids:
            raise TypedMaterializationError("typed materialization contracts must cover exactly the target architecture")
        contract_by_id = {contract.node_id: contract for contract in contracts}
        for node in architecture.nodes:
            contract = contract_by_id[node.node_id]
            if isinstance(contract.transform_plan, TransformPlan) and (
                contract.source_selector != node.selector or contract.transform_plan != node.transform
            ):
                raise TypedMaterializationError(
                    f"typed materialization contract for {node.node_id} does not match the architecture"
                )
        read_view = self.evidence.pin()
        snapshot = read_view.materialize()
        raw_records = tuple(self.builder.build_records(architecture, read_view, contracts))
        evidence_ids = frozenset(row.evidence_id for row in read_view.iter_rows())
        records = validate_materialized_records(
            architecture,
            raw_records,
            evidence_ids=evidence_ids,
        )
        return TypedMaterializedGeneration(
            generation,
            base_generation,
            candidate_id,
            architecture,
            snapshot.sequence,
            snapshot.digest,
            records,
        )

    @staticmethod
    def _validate_records(
        architecture: MemoryArchitectureSpec,
        records: tuple[NodePartitionedRecord, ...],
        *,
        evidence_ids: frozenset[str] | None = None,
    ) -> tuple[NodePartitionedRecord, ...]:
        return validate_materialized_records(architecture, records, evidence_ids=evidence_ids)



__all__ = [
    "TypedNodeBuilderPort",
    "PinnedEvidenceMaterializationSource",
    "TypedMaterializerAdapter",
    "TypedMemoryMaterializer",
]
