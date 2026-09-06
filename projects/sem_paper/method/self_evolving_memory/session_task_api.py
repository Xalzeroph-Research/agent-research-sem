from __future__ import annotations

from research_platform.platform.kernel import ExecutionContext
from research_platform.participant.method.api import MethodTaskCompletionReceipt, MethodTaskOutcome

from .session_context import SEMSessionContextTracker
from .session_evolution_api import EvolutionReconciliation
from .task_coordination import SEMTaskCompletionCoordinator


class SEMSessionTaskAPI:
    """Owns Method-facing task completion/reconciliation over the SEM task coordinator."""

    def __init__(
        self,
        tasks: SEMTaskCompletionCoordinator,
        context: SEMSessionContextTracker,
        generation_provider,
    ) -> None:
        self._tasks = tasks
        self._context = context
        self._generation_provider = generation_provider

    def task_completed(
        self,
        completion_key: str,
        outcome: MethodTaskOutcome | None,
        context: ExecutionContext,
    ) -> MethodTaskCompletionReceipt:
        self._context.update(context)
        self._tasks.task_completed(context, outcome)
        return MethodTaskCompletionReceipt(completion_key, self._generation_provider())

    def reconcile_task(
        self,
        task_key: str,
        context: ExecutionContext,
    ) -> EvolutionReconciliation:
        self._context.update(context)
        return self._tasks.reconcile_task(task_key, context)

    def reconcile_task_completion(
        self,
        completion_key: str,
        context: ExecutionContext,
    ) -> MethodTaskCompletionReceipt | None:
        self._context.update(context)
        return self._tasks.completion_receipt(completion_key, context)


__all__ = ["SEMSessionTaskAPI"]
