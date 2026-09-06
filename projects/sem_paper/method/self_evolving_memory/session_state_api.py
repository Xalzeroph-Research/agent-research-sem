from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from research_platform.platform.kernel import ExecutionContext, JsonValue
from research_platform.platform.kernel.durability import DurableObjectStorePort

from .evidence_api import EvidenceReadPort
from .session_reducer import SEMSessionState
from .session_snapshot_contracts import SEMSessionStateSnapshot, SessionMutationRecord


class SEMSessionClosed(RuntimeError):
    pass


class PreparedSessionAdoptionPort(Protocol):
    """One already-validated adoption transaction, ready for authoritative commit.

    Candidate preparation and evaluation stay outside the session state boundary.
    The cell receives only the minimal commit capability so it can serialize the
    durable generation change with publication to live serving readers.
    """

    def commit(self) -> str: ...


class SEMSessionStatePort(Protocol):
    """Minimal runtime state surface consumed by SEM session subsystems."""

    def open_serving_cut(self) -> tuple[str, EvidenceReadPort]: ...
    def current_generation(self) -> str: ...
    def evolution_summary(self) -> tuple[str, int, str, int, int]: ...
    def ingest(self, payload: JsonValue, context: ExecutionContext | None = None) -> SessionMutationRecord: ...
    def task_completed(self, context: ExecutionContext | None = None) -> SessionMutationRecord: ...
    def commit_prepared_adoption(
        self,
        adoption: PreparedSessionAdoptionPort,
        context: ExecutionContext | None = None,
    ) -> tuple[str, SessionMutationRecord]: ...
    def sync_adopted_generation(
        self, generation: str, context: ExecutionContext | None = None
    ) -> SessionMutationRecord: ...
    def snapshot_state(self) -> SEMSessionStateSnapshot: ...
    def restore(self, snapshot: SEMSessionStateSnapshot) -> SessionMutationRecord: ...
    def close(self) -> None: ...
    def mutation_history(self, *, limit: int = 64) -> tuple[SessionMutationRecord, ...]: ...
    def diagnostics(self) -> dict[str, Any]: ...


class SEMSessionStateFactory(Protocol):
    @property
    def backend_id(self) -> str: ...

    def create(self, session_id: str) -> SEMSessionStatePort: ...


class SEMSessionSnapshotStorePort(DurableObjectStorePort[SEMSessionStateSnapshot], Protocol):
    """Durable snapshot seam consumed by the session-state composition root."""


class SEMSessionSnapshotStoreFactoryPort(Protocol):
    """Build a persistence adapter for one session identity."""

    def __call__(self, path: Path) -> SEMSessionSnapshotStorePort: ...


__all__ = [
    "PreparedSessionAdoptionPort",
    "SEMSessionClosed",
    "SEMSessionStateFactory",
    "SEMSessionStatePort",
    "SEMSessionSnapshotStorePort",
    "SEMSessionSnapshotStoreFactoryPort",
]
