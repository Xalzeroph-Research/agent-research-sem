from __future__ import annotations

from research_platform.platform.kernel import ExecutionContext
from research_platform.participant.method.api import MethodTaskOutcome

from .evolution import DiagnosticTelemetryPort
from .session_evolution_api import EvolutionReconciliation, SessionEvolutionController
from .session_observation import SessionMutationObservationPublisher
from .task_execution import SEMTaskExecution
from .task_lifecycle import SEMTaskLifecycle, TaskProgress
from .task_ports import SEMEvolutionPostCommitError, SEMEvolutionRecoveryRequired, TaskScientificMutationPort
from .task_recovery import SEMTaskRecovery


class SEMTaskCompletionCoordinator:
    """Small façade sharing one lifecycle between normal execution and explicit recovery."""

    def __init__(
        self,
        mutations: TaskScientificMutationPort,
        evolution: SessionEvolutionController,
        observations: SessionMutationObservationPublisher,
        telemetry: DiagnosticTelemetryPort,
        lifecycle: SEMTaskLifecycle | None = None,
    ) -> None:
        self.lifecycle = lifecycle or SEMTaskLifecycle()
        self.execution = SEMTaskExecution(
            mutations,
            evolution,
            observations,
            telemetry,
            self.lifecycle,
        )
        self.recovery = SEMTaskRecovery(mutations, evolution, observations, self.lifecycle)

    def task_completed(
        self,
        context: ExecutionContext,
        outcome: MethodTaskOutcome | None = None,
    ) -> None:
        self.execution.execute(context, outcome)

    def reconcile_task(
        self, task_key: str, context: ExecutionContext
    ) -> EvolutionReconciliation:
        return self.recovery.reconcile(task_key, context)

    def completion_receipt(self, task_key: str, context: ExecutionContext):
        """Read-only proof of a fully completed SEM task, if present."""
        from research_platform.participant.method.api import MethodTaskCompletionReceipt
        from .task_lifecycle import TaskPhase

        progress = self.lifecycle.get(task_key)
        if progress is None or progress.phase is not TaskPhase.COMPLETED:
            return None
        generation = progress.final_generation or progress.base_generation
        return MethodTaskCompletionReceipt(task_key, generation)

    def snapshot(self) -> tuple[TaskProgress, ...]:
        return self.lifecycle.snapshot()

    def restore(self, rows: tuple[TaskProgress, ...]) -> None:
        self.lifecycle.restore(rows)

    def diagnostics(self) -> dict[str, object]:
        return {
            "task_phase_counts": self.lifecycle.phase_counts(),
            "task_terminal_reason_counts": self.lifecycle.terminal_reason_counts(),
        }


__all__ = [
    "SEMEvolutionPostCommitError",
    "SEMEvolutionRecoveryRequired",
    "SEMTaskCompletionCoordinator",
    "TaskScientificMutationPort",
]
