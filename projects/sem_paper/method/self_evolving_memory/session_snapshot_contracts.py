from __future__ import annotations

from dataclasses import dataclass

from research_platform.participant.method.api import MethodObservation

from .evidence_api import EvidenceSnapshot
from .evolution import TelemetrySnapshot
from .session_reducer import SEMSessionState
from .serving import ServingRuntimeState
from .task_lifecycle import TaskProgress


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


SCHEMA_VERSION = "10"
IMPLEMENTATION_VERSION = "0.31.0"


@dataclass(frozen=True, slots=True)
class SessionMutationRecord:
    revision: int
    mutation_type: str
    before_state_digest: str
    after_state_digest: str
    before_evidence_digest: str
    after_evidence_digest: str
    before_closed: bool
    after_closed: bool
    evidence_sequence: int
    architecture_generation: str
    source_revision: int | None = None
    run_id: str | None = None
    task_id: str | None = None
    decision_cycle_id: str | None = None
    operation_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision <= 0:
            raise ValueError("SEM mutation revision must be a positive integer")
        if not isinstance(self.mutation_type, str) or not self.mutation_type.strip():
            raise ValueError("SEM mutation type must be a non-empty string")
        for label, digest in (
            ("before state", self.before_state_digest),
            ("after state", self.after_state_digest),
            ("before evidence", self.before_evidence_digest),
            ("after evidence", self.after_evidence_digest),
        ):
            if not _is_sha256(digest):
                raise ValueError(f"SEM mutation {label} digest must be a lower-case SHA-256 digest")
        if not isinstance(self.before_closed, bool) or not isinstance(self.after_closed, bool):
            raise ValueError("SEM mutation closed flags must be boolean")
        if (
            isinstance(self.evidence_sequence, bool)
            or not isinstance(self.evidence_sequence, int)
            or self.evidence_sequence < 0
        ):
            raise ValueError("SEM mutation evidence sequence must be a non-negative integer")
        if not isinstance(self.architecture_generation, str) or not self.architecture_generation.strip():
            raise ValueError("SEM mutation architecture generation must be a non-empty string")
        if self.source_revision is not None and (
            isinstance(self.source_revision, bool)
            or not isinstance(self.source_revision, int)
            or self.source_revision < 0
        ):
            raise ValueError("SEM mutation source revision must be a non-negative integer when present")
        for label, value in (
            ("run_id", self.run_id),
            ("task_id", self.task_id),
            ("decision_cycle_id", self.decision_cycle_id),
            ("operation_id", self.operation_id),
            ("trace_id", self.trace_id),
            ("span_id", self.span_id),
        ):
            if value is not None and not isinstance(value, str):
                raise ValueError(f"SEM mutation {label} must be a string when present")


@dataclass(frozen=True, slots=True)
class SessionLineageSnapshot:
    revision: int
    mutation_tail: tuple[SessionMutationRecord, ...]

    def __post_init__(self) -> None:
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 0:
            raise ValueError("SEM lineage revision must be a non-negative integer")
        if not isinstance(self.mutation_tail, tuple):
            raise ValueError("SEM mutation tail must be a tuple")
        if self.mutation_tail and (
            not isinstance(self.mutation_tail[-1], SessionMutationRecord)
            or self.mutation_tail[-1].revision > self.revision
        ):
            raise ValueError("SEM mutation tail exceeds lineage revision")


@dataclass(frozen=True, slots=True)
class SEMSessionStateSnapshot:
    """Snapshot owned exclusively by the SEM session-state subsystem."""

    state: SEMSessionState
    evidence: EvidenceSnapshot
    lineage: SessionLineageSnapshot

    def __post_init__(self) -> None:
        if not isinstance(self.state, SEMSessionState):
            raise ValueError("SEM session snapshot state is invalid")
        if not isinstance(self.evidence, EvidenceSnapshot):
            raise ValueError("SEM session snapshot evidence is invalid")
        if not isinstance(self.lineage, SessionLineageSnapshot):
            raise ValueError("SEM session snapshot lineage is invalid")
        if self.state.evidence_sequence != self.evidence.sequence:
            raise ValueError("SEM snapshot state/evidence sequence mismatch")


@dataclass(frozen=True, slots=True)
class SEMSnapshotPayload:
    """Method-level checkpoint payload composed from independent session subsystems."""

    session_state: SEMSessionStateSnapshot
    pending_observations: tuple[MethodObservation, ...]
    task_progress: tuple[TaskProgress, ...]
    evolution_telemetry: TelemetrySnapshot
    serving_state: ServingRuntimeState


__all__ = [
    "IMPLEMENTATION_VERSION",
    "SCHEMA_VERSION",
    "SEMSessionStateSnapshot",
    "SEMSnapshotPayload",
    "SessionLineageSnapshot",
    "SessionMutationRecord",
]
