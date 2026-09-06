from __future__ import annotations

from typing import Protocol

from research_platform.platform.kernel import ExecutionContext

from .session_snapshot_contracts import SessionMutationRecord


class SEMEvolutionPostCommitError(RuntimeError):
    """Task completion is committed, but evolution/adoption completion is uncertain."""

    def __init__(self, task_key: str, cause: BaseException) -> None:
        super().__init__(f"SEM evolution became uncertain after task commit: {task_key}")
        self.cause_type = type(cause).__name__
        self.task_key = task_key
        self.cause = cause
        self.task_completion_committed = True
        self.evolution_uncertain = True
        self.recommended_recovery = "reconcile_method_state"

    @property
    def failure_correlation_refs(self) -> tuple[str, ...]:
        refs = getattr(self.cause, "failure_correlation_refs", ())
        return tuple(refs) if isinstance(refs, tuple) else ()


class SEMEvolutionRecoveryRequired(RuntimeError):
    def __init__(self, task_key: str) -> None:
        super().__init__(f"SEM task has uncertain prior evolution; reconcile before retry: {task_key}")
        self.task_key = task_key
        self.task_completion_committed = True
        self.evolution_uncertain = True
        self.recommended_recovery = "reconcile_method_state"


class TaskScientificMutationPort(Protocol):
    def commit_task_completed(self, context: ExecutionContext) -> tuple[SessionMutationRecord, str]: ...
    def sync_adopted_generation(self, generation: str, context: ExecutionContext) -> SessionMutationRecord: ...


__all__ = [
    "SEMEvolutionPostCommitError",
    "SEMEvolutionRecoveryRequired",
    "TaskScientificMutationPort",
]
