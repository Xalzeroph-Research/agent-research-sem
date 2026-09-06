from __future__ import annotations

from collections.abc import Iterable

from ..deluxe.api.contracts import DeluxeArchitectureSnapshot, DeluxeNodeDescriptor
from ..deluxe.api.ports import DeluxeMemoryRecord, DeluxeReadSnapshot, DeluxeServingSource
from .contracts import MemoryArchitectureSpec
from .canonical import architecture_digest
from .validation import ArchitectureValidator
from .records import NodePartitionedRecord


class ArchitectureProjectionError(ValueError):
    """A node projection cannot be constructed without changing semantics."""


def project_deluxe_architecture(
    architecture: MemoryArchitectureSpec,
    *,
    generation: str | None = None,
) -> DeluxeArchitectureSnapshot:
    ArchitectureValidator().verify(architecture)
    return DeluxeArchitectureSnapshot(
        generation=generation or f"{architecture.architecture_id}:g{architecture.generation}",
        digest=architecture_digest(architecture),
        generation_number=architecture.generation,
        nodes=tuple(
            DeluxeNodeDescriptor(
                node_id=node.node_id,
                purpose=node.purpose,
                access=tuple(sorted(access.value for access in node.access)),
                # A Deluxe capability advertises the set of output kinds, not
                # one entry per field.  Preserve first-seen schema order while
                # removing repeated types such as the TEXT fields in an
                # experience record.
                output_types=tuple(dict.fromkeys(field.dtype.canonical() for field in node.schema)),
                scope=node.scope.value,
            )
            for node in architecture.nodes
        ),
    )


class NodePartitionedDeluxeSnapshot(DeluxeReadSnapshot):
    """Pinned node projection; no flat evidence rows are interpreted implicitly."""

    def __init__(self, architecture: DeluxeArchitectureSnapshot, records: Iterable[DeluxeMemoryRecord]) -> None:
        self._architecture = architecture
        known_nodes = {node.node_id for node in architecture.nodes}
        partitions: dict[str, list[DeluxeMemoryRecord]] = {node_id: [] for node_id in known_nodes}
        seen: set[str] = set()
        for record in records:
            if record.node_id not in known_nodes:
                raise ArchitectureProjectionError(
                    f"record {record.record_id} names node {record.node_id!r} outside pinned architecture"
                )
            if record.record_id in seen:
                raise ArchitectureProjectionError(f"duplicate projected record id: {record.record_id}")
            if record.sequence < 0:
                raise ArchitectureProjectionError(f"negative projected sequence: {record.record_id}")
            seen.add(record.record_id)
            partitions[record.node_id].append(record)
        self._partitions = {
            node_id: tuple(sorted(rows, key=lambda row: (row.sequence, row.record_id)))
            for node_id, rows in partitions.items()
        }

    @property
    def generation(self) -> str:
        return self._architecture.generation

    @property
    def architecture(self) -> DeluxeArchitectureSnapshot:
        return self._architecture

    def node_ids(self) -> tuple[str, ...]:
        return tuple(node.node_id for node in self._architecture.nodes if self._partitions[node.node_id])

    def iter_records(self, node_id: str):
        if node_id not in {node.node_id for node in self._architecture.nodes}:
            raise ArchitectureProjectionError(f"unknown projected node: {node_id}")
        return iter(self._partitions[node_id])


class NodePartitionedDeluxeSource(DeluxeServingSource):
    """Composition adapter from an already-authoritative node projection."""

    def __init__(self, snapshot: NodePartitionedDeluxeSnapshot) -> None:
        self._snapshot = snapshot

    def open_deluxe_snapshot(self) -> DeluxeReadSnapshot:
        return self._snapshot


__all__ = [
    "ArchitectureProjectionError",
    "NodePartitionedDeluxeSnapshot",
    "NodePartitionedDeluxeSource",
    "NodePartitionedRecord",
    "architecture_digest",
    "project_deluxe_architecture",
]
