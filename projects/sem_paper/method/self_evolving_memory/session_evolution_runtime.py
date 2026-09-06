from __future__ import annotations

from research_platform.platform.kernel import ExecutionContext

from .evolution import DiagnosticTelemetryPort, EvolutionOutcome, EvolutionPipeline
from .session_state_api import SEMSessionStatePort
from .session_evolution_api import (
    EvolutionSessionBinding,
    EvolutionReconciliation,
    EvolutionReconciliationPort,
    EvolutionReconciliationStatus,
    EvolutionSessionSnapshot,
    EvolutionSessionSource,
    SessionAdoptionPublication,
    SessionEvolutionController,
)
from .session_state_api import PreparedSessionAdoptionPort


class ConservativeEvolutionReconciler:
    def reconcile(
        self,
        *,
        task_key: str,
        base_generation: str,
        context: ExecutionContext,
    ) -> EvolutionReconciliation:
        del task_key, base_generation, context
        return EvolutionReconciliation(
            EvolutionReconciliationStatus.UNRESOLVED,
            reason="no authoritative evolution reconciliation port configured",
        )


class ReadOnlyEvolutionSessionSource:
    """Runtime adapter exposing only the evolution read model, never the session cell."""

    def __init__(self, cell: SEMSessionStatePort, telemetry: DiagnosticTelemetryPort) -> None:
        self._cell = cell
        self._telemetry = telemetry

    def snapshot(self) -> EvolutionSessionSnapshot:
        generation, evidence_sequence, evidence_digest, tasks_completed, evolution_epoch = (
            self._cell.evolution_summary()
        )
        return EvolutionSessionSnapshot(
            generation=generation,
            evidence_sequence=evidence_sequence,
            evidence_digest=evidence_digest,
            tasks_completed=tasks_completed,
            evolution_epoch=evolution_epoch,
            telemetry=self._telemetry.snapshot(),
        )


class CellSessionAdoptionAuthority:
    """Minimal adapter serializing durable adoption with the live session cell."""

    def __init__(self, session_id: str, cell: SEMSessionStatePort) -> None:
        if not session_id.strip():
            raise ValueError("SEM adoption authority requires session identity")
        self._session_id = session_id
        self._cell = cell

    @property
    def session_id(self) -> str:
        return self._session_id

    def open_evidence_cut(self):
        return self._cell.open_serving_cut()

    def commit_prepared_adoption(
        self,
        adoption: PreparedSessionAdoptionPort,
        context: ExecutionContext,
    ) -> SessionAdoptionPublication:
        generation, mutation = self._cell.commit_prepared_adoption(adoption, context)
        return SessionAdoptionPublication(generation, mutation)


class DisabledSessionEvolution:
    """Explicit no-evolution provider; absence of evolution never triggers hidden behavior."""

    def on_task_completed(self, context: ExecutionContext) -> EvolutionOutcome | None:
        del context
        return None

    def reconcile_uncertain(
        self,
        *,
        task_key: str,
        base_generation: str,
        context: ExecutionContext,
    ) -> EvolutionReconciliation:
        del task_key, context
        return EvolutionReconciliation(
            EvolutionReconciliationStatus.NO_AUTHORITATIVE_ADOPTION,
            authoritative_generation=base_generation,
            reason="evolution is disabled",
        )


class DisabledSessionEvolutionFactory:
    def __call__(self, binding: EvolutionSessionBinding) -> SessionEvolutionController:
        del binding
        return DisabledSessionEvolution()


class PipelineSessionEvolution:
    """Runtime adapter only; scientific and reconciliation authority stay in injected ports."""

    def __init__(
        self,
        pipeline: EvolutionPipeline,
        reconciliation: EvolutionReconciliationPort | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._reconciliation = reconciliation or ConservativeEvolutionReconciler()

    def on_task_completed(self, context: ExecutionContext) -> EvolutionOutcome:
        return self._pipeline.run(context)

    def reconcile_uncertain(
        self,
        *,
        task_key: str,
        base_generation: str,
        context: ExecutionContext,
    ) -> EvolutionReconciliation:
        return self._reconciliation.reconcile(
            task_key=task_key,
            base_generation=base_generation,
            context=context,
        )


__all__ = [
    "ConservativeEvolutionReconciler",
    "CellSessionAdoptionAuthority",
    "DisabledSessionEvolution",
    "DisabledSessionEvolutionFactory",
    "PipelineSessionEvolution",
    "ReadOnlyEvolutionSessionSource",
]
