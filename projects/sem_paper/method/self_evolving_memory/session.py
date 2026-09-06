from __future__ import annotations

from research_platform.platform.kernel import ExecutionContext
from research_platform.participant.method.api import (
    MethodSnapshot,
    MethodTaskCompletionReceipt,
    MethodTaskOutcome,
    RecallRequest,
    RecallResult,
)

from .session_assembly import SEMSessionRuntime
from .session_state_api import SEMSessionClosed
from .session_evolution_api import EvolutionReconciliation
from .session_operation_gate import SEMSessionOperationGate, SEMSessionRestoreFaulted
from .task_coordination import SEMEvolutionPostCommitError, SEMEvolutionRecoveryRequired
from .task_lifecycle import SEMTaskLifecycle


class SEMSession:
    """Method ABI facade over an already-composed SEM session runtime.

    The ABI facade is also the outermost concurrency boundary. Every operation
    that can read or mutate checkpoint-relevant method state is serialized so a
    checkpoint is one coherent method cut rather than a sequence of unrelated
    component snapshots.
    """

    METHOD_ID = "self_evolving_memory"
    task_completion_idempotency = "sem_task_lifecycle.v1"

    @staticmethod
    def task_completion_key(context: ExecutionContext) -> str:
        return SEMTaskLifecycle.key(context)

    def __init__(self, session_id: str, runtime: SEMSessionRuntime) -> None:
        self.session_id = session_id
        self._runtime = runtime
        self._operations = SEMSessionOperationGate()

    @property
    def generation(self) -> str:
        with self._operations.operation():
            return self._runtime.lifecycle.generation

    def ingest(self, evidence: object, context: ExecutionContext) -> None:
        with self._operations.operation():
            self._runtime.ingest.ingest(evidence, context)

    def recall(self, request: RecallRequest) -> RecallResult:
        with self._operations.operation():
            return self._runtime.serving.recall(request)

    def task_completed(
        self,
        result: object,
        context: ExecutionContext,
    ) -> MethodTaskCompletionReceipt:
        outcome = result if isinstance(result, MethodTaskOutcome) else None
        with self._operations.operation():
            return self._runtime.tasks.task_completed(
                self.task_completion_key(context),
                outcome,
                context,
            )

    def reconcile_task(
        self,
        task_key: str,
        context: ExecutionContext,
    ) -> EvolutionReconciliation:
        with self._operations.operation():
            return self._runtime.tasks.reconcile_task(task_key, context)

    def reconcile_task_completion(
        self,
        completion_key: str,
        context: ExecutionContext,
    ) -> MethodTaskCompletionReceipt | None:
        with self._operations.operation():
            return self._runtime.tasks.reconcile_task_completion(completion_key, context)

    def checkpoint(self) -> MethodSnapshot:
        with self._operations.operation():
            return self._runtime.persistence.checkpoint()

    def restore(self, snapshot: MethodSnapshot) -> None:
        with self._operations.operation():
            decoded = self._runtime.persistence.prepare_restore(snapshot)
            try:
                record = self._runtime.persistence.apply_prepared_restore(decoded)
            except BaseException as exc:
                self._operations.mark_restore_failure(exc)
                raise
            # Observation publication occurs after authoritative restore apply.
            # An outbox delivery failure keeps its normal committed-mutation
            # semantics and does not poison a successfully restored session.
            self._runtime.persistence.publish_restore(record)

    def flush_observations(self) -> tuple[str, ...]:
        with self._operations.operation():
            return self._runtime.lifecycle.flush_observations()

    def mutation_history(self, *, limit: int = 64):
        with self._operations.operation(allow_restore_fault=True):
            return self._runtime.lifecycle.mutation_history(limit=limit)

    def diagnostics(self) -> dict[str, object]:
        with self._operations.operation(allow_restore_fault=True):
            result = self._runtime.lifecycle.diagnostics()
            fault = self._operations.restore_fault
            result["restore_fault"] = None if fault is None else {
                "error_type": fault.error_type,
                "error_digest": fault.error_digest,
            }
            return result

    def close(self) -> None:
        with self._operations.operation(allow_restore_fault=True):
            self._runtime.lifecycle.close()


__all__ = [
    "SEMSession",
    "SEMSessionClosed",
    "SEMSessionRestoreFaulted",
    "SEMEvolutionPostCommitError",
    "SEMEvolutionRecoveryRequired",
]
