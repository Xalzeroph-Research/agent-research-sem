from __future__ import annotations

from .evolution import TelemetryBook
from .evidence_integrity import validate_evidence_snapshot
from .session_snapshot_contracts import SEMSnapshotPayload, SessionLineageSnapshot
from .task_lifecycle import SEMTaskLifecycle


def validate_lineage(lineage: SessionLineageSnapshot) -> None:
    if lineage.revision < 0:
        raise ValueError("SEM snapshot lineage revision must be non-negative")
    previous = max(0, lineage.revision - len(lineage.mutation_tail))
    for record in lineage.mutation_tail:
        if record.revision <= previous:
            raise ValueError("SEM snapshot mutation lineage revisions are not strictly increasing")
        if record.revision > lineage.revision:
            raise ValueError("SEM snapshot mutation lineage exceeds snapshot revision")
        previous = record.revision


def validate_snapshot_payload(payload: SEMSnapshotPayload) -> None:
    validate_evidence_snapshot(payload.session_state.evidence)
    if payload.session_state.state.evidence_sequence != payload.session_state.evidence.sequence:
        raise ValueError("SEM snapshot state/evidence sequence mismatch")
    validate_lineage(payload.session_state.lineage)
    observation_ids = tuple(row.observation_id for row in payload.pending_observations)
    if len(set(observation_ids)) != len(observation_ids):
        raise ValueError("SEM snapshot contains duplicate pending observation ids")
    task_keys = tuple(row.task_key for row in payload.task_progress)
    if len(set(task_keys)) != len(task_keys):
        raise ValueError("SEM snapshot contains duplicate task progress keys")
    # Validate every restorable component before the live session mutates.
    # These temporary owners exercise the same schema/invariant checks as the
    # actual restore path without publishing observations or changing state.
    SEMTaskLifecycle().restore(payload.task_progress)
    TelemetryBook().restore(payload.evolution_telemetry)
