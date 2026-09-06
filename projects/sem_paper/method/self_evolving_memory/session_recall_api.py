from __future__ import annotations

from research_platform.participant.method.api import RecallRequest, RecallResult

from .evolution import DiagnosticTelemetryPort, QueryRecordObservation
from .session_serving_api import SessionServingPort
from .serving import ServingRuntimeState


class SEMSessionRecallAPI:
    """Method-facing recall plus architecture-neutral query observation.

    Serving remains the only retrieval authority. This adapter merely copies
    returned facts into the session-owned diagnostic book. Recalls made
    outside a task are served normally but do not advance task-scoped
    evolution evidence.
    """

    def __init__(self, serving: SessionServingPort, telemetry: DiagnosticTelemetryPort) -> None:
        self._serving = serving
        self._telemetry = telemetry

    def snapshot_state(self) -> ServingRuntimeState:
        return self._serving.snapshot_state()

    def validate_state(self, snapshot: ServingRuntimeState) -> None:
        self._serving.validate_state(snapshot)

    def restore_state(self, snapshot: ServingRuntimeState) -> None:
        self._serving.restore_state(snapshot)

    def recall(self, request: RecallRequest) -> RecallResult:
        if not isinstance(request, RecallRequest):
            raise TypeError("SEM recall requires RecallRequest")
        served = self._serving.recall(request.intent, limit=request.limit)
        task_id = request.context.task_id
        if task_id:
            records = tuple(
                QueryRecordObservation(
                    node_id=row.node_id,
                    record_id=row.record_id,
                    score=row.score,
                    payload=dict(row.payload),
                    source_refs=tuple(row.source_refs),
                )
                for row in served.diagnostic_records
            )
            self._telemetry.record_query(
                task_id=task_id,
                intent=request.intent,
                opportunity_key=request.context.decision_cycle_id,
                selected_nodes=tuple(served.selected_nodes),
                records=records,
            )
        return RecallResult(served.context_text, served.generation)


__all__ = ["SEMSessionRecallAPI"]
