from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from research_platform.platform.kernel import ExecutionContext

from .evidence_api import EvidenceReadPort
from .evolution import EvolutionOutcome, TelemetrySnapshot
from .session_state_api import PreparedSessionAdoptionPort
from .session_snapshot_contracts import SessionMutationRecord


class EvolutionReconciliationStatus(StrEnum):
    NO_AUTHORITATIVE_ADOPTION = "no_authoritative_adoption"
    ADOPTION_CONFIRMED = "adoption_confirmed"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class EvolutionReconciliation:
    status: EvolutionReconciliationStatus
    authoritative_generation: str | None = None
    evidence_refs: tuple[str, ...] = ()
    reason: str | None = None


class EvolutionReconciliationPort(Protocol):
    def reconcile(
        self,
        *,
        task_key: str,
        base_generation: str,
        context: ExecutionContext,
    ) -> EvolutionReconciliation: ...


@dataclass(frozen=True, slots=True)
class EvolutionSessionSnapshot:
    generation: str
    evidence_sequence: int
    evidence_digest: str
    tasks_completed: int
    evolution_epoch: int
    telemetry: TelemetrySnapshot


class EvolutionSessionSource(Protocol):
    def snapshot(self) -> EvolutionSessionSnapshot: ...


@dataclass(frozen=True, slots=True)
class SessionAdoptionPublication:
    """Exact session publication produced by one authoritative adoption commit."""

    generation: str
    mutation: SessionMutationRecord


class SessionAdoptionAuthority(Protocol):
    """Narrow session authority granted only to the adoption stage."""

    @property
    def session_id(self) -> str: ...

    def open_evidence_cut(self) -> tuple[str, EvidenceReadPort]: ...

    def commit_prepared_adoption(
        self,
        adoption: PreparedSessionAdoptionPort,
        context: ExecutionContext,
    ) -> SessionAdoptionPublication: ...


@dataclass(frozen=True, slots=True)
class EvolutionSessionBinding:
    """Session-scoped read and adoption capabilities with explicit separation."""

    source: EvolutionSessionSource
    adoption: SessionAdoptionAuthority

    def snapshot(self) -> EvolutionSessionSnapshot:
        """Compatibility read surface; never exposes adoption to read-only stages."""

        return self.source.snapshot()


class SessionEvolutionController(Protocol):
    def on_task_completed(self, context: ExecutionContext) -> EvolutionOutcome | None: ...

    def reconcile_uncertain(
        self,
        *,
        task_key: str,
        base_generation: str,
        context: ExecutionContext,
    ) -> EvolutionReconciliation: ...


class SessionEvolutionFactory(Protocol):
    def __call__(self, binding: EvolutionSessionBinding) -> SessionEvolutionController: ...


__all__ = [
    "EvolutionReconciliation",
    "EvolutionReconciliationPort",
    "EvolutionReconciliationStatus",
    "EvolutionSessionBinding",
    "EvolutionSessionSnapshot",
    "EvolutionSessionSource",
    "SessionAdoptionAuthority",
    "SessionAdoptionPublication",
    "SessionEvolutionController",
    "SessionEvolutionFactory",
]
