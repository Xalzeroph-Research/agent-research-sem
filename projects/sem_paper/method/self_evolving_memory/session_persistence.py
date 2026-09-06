from __future__ import annotations

from research_platform.participant.method.api import MethodRuntimeBinding, MethodSnapshot

from .evolution import DiagnosticTelemetryPort
from .session_state_api import SEMSessionStatePort
from .session_context import SEMSessionContextTracker
from .session_observation import SessionMutationObservationPublisher
from .session_recall_api import SEMSessionRecallAPI
from .session_snapshot_codec import SEMSnapshotCodec
from .session_snapshot_contracts import SCHEMA_VERSION, SEMSnapshotPayload, SessionMutationRecord
from .task_coordination import SEMTaskCompletionCoordinator


class SEMSessionPersistence:
    """Owns SEM snapshot/checkpoint orchestration and restore publication only.

    Restore is intentionally split into prepare/apply/publish phases. ``prepare``
    is side-effect free; ``apply`` may mutate scientific/session-local owners;
    ``publish`` is observation-only and therefore must not decide whether the
    scientific restore itself succeeded.
    """

    def __init__(
        self,
        session_id: str,
        cell: SEMSessionStatePort,
        observations: SessionMutationObservationPublisher,
        tasks: SEMTaskCompletionCoordinator,
        context: SEMSessionContextTracker,
        method_binding: MethodRuntimeBinding,
        telemetry: DiagnosticTelemetryPort,
        serving: SEMSessionRecallAPI,
    ) -> None:
        self._session_id = session_id
        self._cell = cell
        self._observations = observations
        self._tasks = tasks
        self._context = context
        self._codec = SEMSnapshotCodec(method_binding)
        self._telemetry = telemetry
        self._serving = serving

    @property
    def schema_version(self) -> str:
        return SCHEMA_VERSION

    def checkpoint(self) -> MethodSnapshot:
        payload = SEMSnapshotPayload(
            self._cell.snapshot_state(),
            self._observations.snapshot(),
            self._tasks.snapshot(),
            self._telemetry.snapshot(),
            self._serving.snapshot_state(),
        )
        return self._codec.dump(self._session_id, payload)

    def prepare_restore(self, snapshot: MethodSnapshot) -> SEMSnapshotPayload:
        """Decode and validate a snapshot without mutating any live owner."""

        decoded = self._codec.load(snapshot, session_id=self._session_id)
        self._serving.validate_state(decoded.serving_state)
        return decoded

    def apply_prepared_restore(self, decoded: SEMSnapshotPayload) -> SessionMutationRecord:
        """Apply one already-validated snapshot; caller owns the failure barrier.

        The order keeps the authoritative session-state swap last. If an earlier
        derived/observation owner rejects the prepared state, session truth has
        not yet moved. If any apply step fails, callers must treat the in-memory
        runtime as uncertain because exact rollback is not generally possible.
        """

        self._serving.restore_state(decoded.serving_state)
        self._observations.restore(decoded.pending_observations)
        self._tasks.restore(decoded.task_progress)
        self._telemetry.restore(decoded.evolution_telemetry)
        return self._cell.restore(decoded.session_state)

    def publish_restore(self, record: SessionMutationRecord) -> None:
        """Publish the committed restore mutation through the observation outbox."""

        self._observations.emit(record, self._context.current)

    def restore(self, snapshot: MethodSnapshot) -> None:
        """Compatibility entry point for callers that do not need fault fencing."""

        decoded = self.prepare_restore(snapshot)
        record = self.apply_prepared_restore(decoded)
        self.publish_restore(record)


__all__ = ["SEMSessionPersistence"]
