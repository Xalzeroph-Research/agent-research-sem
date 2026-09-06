from __future__ import annotations

from research_platform.platform.kernel import ExecutionContext

from .session_evolution_api import (
    EvolutionReconciliation,
    EvolutionReconciliationStatus,
    SessionEvolutionController,
)
from .session_observation import SessionMutationObservationPublisher
from .task_lifecycle import SEMTaskLifecycle, TaskLifecycleConflict, TaskPhase
from .task_ports import SEMEvolutionRecoveryRequired, TaskScientificMutationPort


class SEMTaskRecovery:
    """Recovery-only authority; normal task execution cannot invoke its decisions implicitly."""

    def __init__(
        self,
        mutations: TaskScientificMutationPort,
        evolution: SessionEvolutionController,
        observations: SessionMutationObservationPublisher,
        lifecycle: SEMTaskLifecycle,
    ) -> None:
        self.mutations = mutations
        self.evolution = evolution
        self.observations = observations
        self.lifecycle = lifecycle

    def _probe(
        self,
        *,
        task_key: str,
        base_generation: str,
        context: ExecutionContext,
    ) -> EvolutionReconciliation:
        return self.evolution.reconcile_uncertain(
            task_key=task_key,
            base_generation=base_generation,
            context=context,
        )

    def _apply_confirmed_adoption(
        self,
        task_key: str,
        base_generation: str,
        generation: str | None,
        context: ExecutionContext,
    ) -> None:
        if not generation or generation == base_generation:
            raise TaskLifecycleConflict(
                "confirmed adoption requires an advanced authoritative generation"
            )
        record = self.mutations.sync_adopted_generation(generation, context)
        self.lifecycle.transition(
            task_key,
            expected=TaskPhase.EVOLUTION_UNCERTAIN,
            target=TaskPhase.ADOPTION_OBSERVATION_PENDING,
            final_generation=generation,
        )
        self.observations.emit(record, context)
        self.lifecycle.transition(
            task_key,
            expected=TaskPhase.ADOPTION_OBSERVATION_PENDING,
            target=TaskPhase.COMPLETED,
        )

    def reconcile(
        self,
        task_key: str,
        context: ExecutionContext,
    ) -> EvolutionReconciliation:
        progress = self.lifecycle.get(task_key)
        if progress is None or progress.phase is not TaskPhase.EVOLUTION_UNCERTAIN:
            actual = progress.phase.value if progress is not None else "missing"
            raise TaskLifecycleConflict(
                f"SEM task is not awaiting evolution reconciliation: {actual}"
            )
        result = self._probe(
            task_key=task_key,
            base_generation=progress.base_generation,
            context=context,
        )
        if result.status is EvolutionReconciliationStatus.NO_AUTHORITATIVE_ADOPTION:
            self.lifecycle.complete_after_failed_evolution(
                task_key, reason="evolution_failed_no_authoritative_adoption"
            )
            return result
        if result.status is EvolutionReconciliationStatus.ADOPTION_CONFIRMED:
            self._apply_confirmed_adoption(
                task_key,
                progress.base_generation,
                result.authoritative_generation,
                context,
            )
            return result
        raise SEMEvolutionRecoveryRequired(task_key)


__all__ = ["SEMTaskRecovery"]
