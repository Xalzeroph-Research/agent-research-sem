from __future__ import annotations

from typing import Protocol

from .serving import MemoryReadSnapshot, MemoryServingRecord, ServingRuntimeState
from .deluxe.api.ports import DeluxeServingSource, DeluxeReadSnapshot
from .session_state_api import SEMSessionStatePort


class ServingSessionSource(Protocol):
    """Pinned read source exposed to scientific serving providers."""

    def open_snapshot(self) -> MemoryReadSnapshot: ...


class SessionServingResultPort(Protocol):
    """Provider-neutral recall result consumed by the session adapter."""

    generation: str
    context_text: str
    selected_nodes: tuple[str, ...]
    diagnostic_records: tuple[MemoryServingRecord, ...]


class SessionServingPort(Protocol):
    def recall(self, intent: str, *, limit: int) -> SessionServingResultPort: ...
    def snapshot_state(self) -> ServingRuntimeState: ...
    def validate_state(self, snapshot: ServingRuntimeState) -> None: ...
    def restore_state(self, snapshot: ServingRuntimeState) -> None: ...


class SessionServingFactory(Protocol):
    def __call__(self, source: ServingSessionSource) -> SessionServingPort: ...


class DeluxeServingSessionSource(ServingSessionSource, Protocol):
    """Session source for an explicit Deluxe treatment."""

    def open_deluxe_snapshot(self) -> DeluxeReadSnapshot: ...


class DeluxeSnapshotFactory(Protocol):
    def __call__(self, state: SEMSessionStatePort) -> DeluxeServingSource: ...


class DeluxeSessionServingFactory(Protocol):
    def __call__(self, source: DeluxeServingSessionSource) -> SessionServingPort: ...


__all__ = [
    "DeluxeSessionServingFactory",
    "DeluxeServingSessionSource",
    "DeluxeSnapshotFactory",
    "ServingSessionSource",
    "SessionServingFactory",
    "SessionServingPort",
    "SessionServingResultPort",
]
