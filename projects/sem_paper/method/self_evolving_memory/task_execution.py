from __future__ import annotations

from research_platform.platform.kernel import ExecutionContext
from research_platform.participant.method.api import MethodTaskOutcome

from .evolution import DiagnosticTelemetryPort, TaskObservation
from .session_evolution_api import SessionEvolutionController
from .session_observation import SessionMutationObservationPublisher
from .task_lifecycle import SEMTaskLifecycle, TaskLifecycleConflict, TaskPhase
from .task_ports import SEMEvolutionPostCommitError, SEMEvolutionRecoveryRequired, TaskScientificMutationPort


class SEMTaskExecution:
    """Normal task-completion path; recovery decisions are intentionally elsewhere."""

    def __init__(
        self,
        mutations: TaskScientificMutationPort,
        evolution: SessionEvolutionController,
        observations: SessionMutationObservationPublisher,
        telemetry: DiagnosticTelemetryPort,
        lifecycle: SEMTaskLifecycle,
    ) -> None:
        self.mutations = mutations
        self.evolution = evolution
        self.observations = observations
        self.telemetry = telemetry
        self.lifecycle = lifecycle

    def _record_outcome(
        self,
        outcome: MethodTaskOutcome | None,
        context: ExecutionContext,
    ) -> None:
        if outcome is None:
            return
        if context.task_id and outcome.task_id != context.task_id:
            raise ValueError("SEM task outcome identity does not match ExecutionContext")
        self.telemetry.record_task(
            TaskObservation(
                task_id=outcome.task_id,
                family=outcome.family,
                success=outcome.success,
                utility=outcome.utility,
            )
        )

    def _resume_or_commit_task(self, task_key: str, context: ExecutionContext) -> None:
        progress = self.lifecycle.get(task_key)
        if progress is None:
            record, base_generation = self.mutations.commit_task_completed(context)
            self.lifecycle.begin(task_key, base_generation=base_generation)
            self.observations.emit(record, context)
            self.lifecycle.transition(
                task_key,
                expected=TaskPhase.OBSERVATION_PENDING,
                target=TaskPhase.EVOLUTION_PENDING,
            )
            return
        if progress.phase is TaskPhase.OBSERVATION_PENDING:
            self.observations.flush()
            self.lifecycle.transition(
                task_key,
                expected=TaskPhase.OBSERVATION_PENDING,
                target=TaskPhase.EVOLUTION_PENDING,
            )
            return
        if progress.phase is not TaskPhase.EVOLUTION_PENDING:
            raise TaskLifecycleConflict(f"unexpected SEM task phase: {progress.phase.value}")

    def _run_evolution(self, task_key: str, context: ExecutionContext):
        self.lifecycle.transition(
            task_key,
            expected=TaskPhase.EVOLUTION_PENDING,
            target=TaskPhase.EVOLUTION_UNCERTAIN,
        )
        try:
            outcome = self.evolution.on_task_completed(context)
            if outcome is None or outcome.status != "adopted":
                return outcome, None
            if not outcome.final_generation:
                raise ValueError("adopted evolution outcome requires final generation")
            record = self.mutations.sync_adopted_generation(outcome.final_generation, context)
            return outcome, record
        except Exception as exc:
            raise SEMEvolutionPostCommitError(task_key, exc) from exc

    def _finish(self, task_key: str, context: ExecutionContext, outcome, adoption_record) -> None:
        if adoption_record is None:
            self.lifecycle.transition(
                task_key,
                expected=TaskPhase.EVOLUTION_UNCERTAIN,
                target=TaskPhase.COMPLETED,
            )
            return
        assert outcome is not None and outcome.final_generation is not None
        self.lifecycle.transition(
            task_key,
            expected=TaskPhase.EVOLUTION_UNCERTAIN,
            target=TaskPhase.ADOPTION_OBSERVATION_PENDING,
            final_generation=outcome.final_generation,
        )
        self.observations.emit(adoption_record, context)
        self.lifecycle.transition(
            task_key,
            expected=TaskPhase.ADOPTION_OBSERVATION_PENDING,
            target=TaskPhase.COMPLETED,
        )

    def execute(
        self,
        context: ExecutionContext,
        task_outcome: MethodTaskOutcome | None = None,
    ) -> None:
        task_key = self.lifecycle.key(context)
        progress = self.lifecycle.get(task_key)
        if progress is not None and progress.phase is TaskPhase.COMPLETED:
            self._record_outcome(task_outcome, context)
            return
        if progress is not None and progress.phase is TaskPhase.EVOLUTION_UNCERTAIN:
            self._record_outcome(task_outcome, context)
            raise SEMEvolutionRecoveryRequired(task_key)
        if progress is not None and progress.phase is TaskPhase.ADOPTION_OBSERVATION_PENDING:
            self.observations.flush()
            self.lifecycle.transition(
                task_key,
                expected=TaskPhase.ADOPTION_OBSERVATION_PENDING,
                target=TaskPhase.COMPLETED,
            )
            self._record_outcome(task_outcome, context)
            return
        self._resume_or_commit_task(task_key, context)
        # Observe only after the authoritative task mutation exists and before
        # evolution reads the diagnostic cut. Retries are exact because the
        # telemetry book rejects outcome drift by task identity.
        self._record_outcome(task_outcome, context)
        evolution_outcome, adoption_record = self._run_evolution(task_key, context)
        self._finish(task_key, context, evolution_outcome, adoption_record)


__all__ = ["SEMTaskExecution"]
