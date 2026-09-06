from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol

from .architecture import MemoryArchitectureSpec, MemoryNodeSpec, SemPaperArchitecturePreset, SourceKind, build_sem_paper_architecture
from .architecture.records import NodePartitionedRecord
from .evidence_api import EvidenceReadPort, EvidenceRecord
from .materialization import MaterializationContract


class TypedSemanticNodeTransformPort(Protocol):
    """Semantic transform seam for one architecture node.

    The adapter may be deterministic or model-backed, but it must return
    grounded records with source references.  The builder never substitutes an
    empty record, a flat evidence row, or an unverified model answer.
    """

    def transform(
        self,
        *,
        node: MemoryNodeSpec,
        source_records: tuple[EvidenceRecord | NodePartitionedRecord, ...],
    ) -> Iterable[NodePartitionedRecord]: ...


class TypedNodeBuilderConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SemPaperTypedMaterializationConfiguration:
    """One explicit current-project architecture plus its transform seam."""

    architecture: MemoryArchitectureSpec
    contracts: tuple[MaterializationContract, ...]
    builder: "ArchitectureDrivenTypedNodeBuilder"


def build_sem_paper_typed_materialization_configuration(
    transformer: TypedSemanticNodeTransformPort,
    *,
    preset: SemPaperArchitecturePreset | str = SemPaperArchitecturePreset.C,
) -> SemPaperTypedMaterializationConfiguration:
    architecture = build_sem_paper_architecture(preset)
    contracts = tuple(
        MaterializationContract(node.node_id, node.selector, node.transform)
        for node in architecture.nodes
    )
    return SemPaperTypedMaterializationConfiguration(
        architecture=architecture,
        contracts=contracts,
        builder=ArchitectureDrivenTypedNodeBuilder(transformer),
    )


class ArchitectureDrivenTypedNodeBuilder:
    """Route typed node transforms according to the current architecture DAG."""

    def __init__(self, transformer: TypedSemanticNodeTransformPort) -> None:
        if not callable(getattr(transformer, "transform", None)):
            raise TypedNodeBuilderConfigurationError("typed node builder requires an explicit semantic transformer")
        self._transformer = transformer

    def build_records(
        self,
        architecture: MemoryArchitectureSpec,
        evidence: EvidenceReadPort,
        contracts: tuple[MaterializationContract, ...],
    ) -> Iterable[NodePartitionedRecord]:
        contract_nodes = {contract.node_id for contract in contracts}
        architecture_nodes = set(architecture.node_map())
        if contract_nodes != architecture_nodes:
            raise TypedNodeBuilderConfigurationError("typed builder contracts must cover the complete architecture")

        built: dict[str, tuple[NodePartitionedRecord, ...]] = {}
        for node_id in architecture.topological_order():
            node = architecture.get(node_id)
            sources: list[EvidenceRecord | NodePartitionedRecord] = []
            for source in node.sources:
                if source.kind is SourceKind.EVIDENCE:
                    sources.extend(self._evidence_sources(evidence, source.event_types))
                elif source.node_id is not None:
                    sources.extend(built[source.node_id])
            records = tuple(self._transformer.transform(node=node, source_records=tuple(sources)))
            for record in records:
                if not isinstance(record, NodePartitionedRecord):
                    raise TypedNodeBuilderConfigurationError(
                        f"semantic transform for {node.node_id} returned a non-typed record"
                    )
                if record.node_id != node.node_id:
                    raise TypedNodeBuilderConfigurationError(
                        f"semantic transform for {node.node_id} returned record for {record.node_id}"
                    )
            built[node_id] = records

        return tuple(record for node_id in architecture.topological_order() for record in built[node_id])

    @staticmethod
    def _evidence_sources(evidence: EvidenceReadPort, event_types: tuple[str, ...]) -> tuple[EvidenceRecord, ...]:
        allowed = frozenset(event_types)
        rows: list[EvidenceRecord] = []
        for row in evidence.iter_rows():
            payload = row.payload
            if not allowed:
                rows.append(row)
                continue
            if isinstance(payload, Mapping) and str(payload.get("event_type", "")) in allowed:
                rows.append(row)
        return tuple(rows)


__all__ = [
    "ArchitectureDrivenTypedNodeBuilder",
    "SemPaperTypedMaterializationConfiguration",
    "TypedNodeBuilderConfigurationError",
    "TypedSemanticNodeTransformPort",
    "build_sem_paper_typed_materialization_configuration",
]
