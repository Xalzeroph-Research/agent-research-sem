from __future__ import annotations

from typing import Iterator

from research_platform.platform.kernel import canonical_text
from .evidence_api import EvidenceReadPort
from .session_serving_api import DeluxeSnapshotFactory, DeluxeServingSessionSource
from .serving import MemoryNodeDocument, MemoryReadSnapshot
from .session_state_api import SEMSessionStatePort


class SessionMemoryReadSnapshot:
    """Pinned SEM serving view; canonical payload text is materialized lazily."""

    __slots__ = ("generation", "_evidence")

    def __init__(self, generation: str, evidence: EvidenceReadPort) -> None:
        self.generation = generation
        self._evidence = evidence

    @property
    def node_count(self) -> int:
        return self._evidence.count

    def latest_node_id(self) -> str | None:
        row = self._evidence.latest()
        return None if row is None else row.evidence_id

    def contains(self, node_id: str) -> bool:
        return self._evidence.contains(node_id)

    def node_ids(self) -> tuple[str, ...]:
        return tuple(row.evidence_id for row in self._evidence.iter_rows())

    def node_sequence(self, node_id: str) -> int | None:
        return self._evidence.sequence_of(node_id)

    def prefix_digest(self, count: int) -> str:
        return self._evidence.prefix_digest(count)

    def iter_node_documents(self, start_position: int = 0) -> Iterator[MemoryNodeDocument]:
        for row in self._evidence.iter_rows(start_position):
            yield MemoryNodeDocument(row.evidence_id, row.sequence, row.digest, canonical_text(row.payload))

    def resolve(self, node_ids: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
        resolved: list[tuple[str, str]] = []
        for node_id in node_ids:
            row = self._evidence.get(node_id)
            if row is not None:
                resolved.append((node_id, canonical_text(row.payload)))
        return tuple(resolved)


class ReadOnlyServingSessionSource:
    """Runtime adapter from session state authority to a pinned serving read source."""

    def __init__(self, cell: SEMSessionStatePort) -> None:
        self._cell = cell

    def open_snapshot(self) -> MemoryReadSnapshot:
        generation, evidence = self._cell.open_serving_cut()
        return SessionMemoryReadSnapshot(generation, evidence)


class ReadOnlyDeluxeServingSessionSource(DeluxeServingSessionSource):
    """Composition adapter for a typed, node-partitioned Deluxe snapshot.

    The provider is project-owned and receives only the state port. This class
    deliberately does not derive nodes from the flat evidence cut.
    """

    def __init__(self, cell: SEMSessionStatePort, snapshot_factory: DeluxeSnapshotFactory) -> None:
        self._cell = cell
        self._provider = snapshot_factory(cell)

    def open_snapshot(self) -> MemoryReadSnapshot:
        generation, evidence = self._cell.open_serving_cut()
        return SessionMemoryReadSnapshot(generation, evidence)

    def open_deluxe_snapshot(self):
        return self._provider.open_deluxe_snapshot()


__all__ = [
    "ReadOnlyDeluxeServingSessionSource",
    "ReadOnlyServingSessionSource",
    "SessionMemoryReadSnapshot",
]
