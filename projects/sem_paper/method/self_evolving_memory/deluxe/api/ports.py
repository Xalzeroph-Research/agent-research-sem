from __future__ import annotations

from typing import Iterator, Mapping, Protocol
from research_platform.platform.kernel import JsonValue

from .contracts import DeluxeArchitectureSnapshot


class DeluxeMemoryRecord(Protocol):
    """Node-partitioned record required by the Deluxe serving path."""

    @property
    def node_id(self) -> str: ...

    @property
    def record_id(self) -> str: ...

    @property
    def sequence(self) -> int: ...

    @property
    def text(self) -> str: ...

    @property
    def payload(self) -> Mapping[str, JsonValue]: ...

    @property
    def source_refs(self) -> tuple[str, ...]: ...


class DeluxeReadSnapshot(Protocol):
    """Pinned node-partitioned read model for Deluxe retrieval."""

    @property
    def generation(self) -> str: ...

    @property
    def architecture(self) -> DeluxeArchitectureSnapshot: ...

    def node_ids(self) -> tuple[str, ...]: ...

    def iter_records(self, node_id: str) -> Iterator[DeluxeMemoryRecord]: ...


class DeluxeServingSource(Protocol):
    """Composition seam; it owns the adapter from scientific state to nodes."""

    def open_deluxe_snapshot(self) -> DeluxeReadSnapshot: ...


__all__ = ["DeluxeMemoryRecord", "DeluxeReadSnapshot", "DeluxeServingSource"]
