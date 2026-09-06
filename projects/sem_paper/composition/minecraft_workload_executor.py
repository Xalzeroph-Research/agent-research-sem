from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Protocol

from research_platform.participant.method.api import MethodSession
from research_platform.platform.kernel import ExecutionContext
from research_platform.experimentation.experiment.api import ExperimentTaskSpec
from research_platform.experimentation.workload import (
    GenericWorkloadBatchExecutor,
    WorkloadBatchBindingPort,
    WorkloadTaskResult,
)
from research_platform.experimentation.checkpoint.api import (
    WorkloadCheckpointBindingPort,
    WorkloadCheckpointCoordinatorPort,
    WorkloadCheckpointedBatchExecutorPort,
)
from research_platform.experimentation.study.api import VariantBinding
from projects.sem_paper.method.self_evolving_memory.evolution import (
    BranchRole,
    CandidateArchitecture,
)

from .minecraft_branch import (
    MinecraftBranchExecutionResult,
    MinecraftBranchExecutorPort,
)
from .minecraft_workload import (
    MinecraftEvidencePort,
    MinecraftPlannerPort,
    MinecraftTaskRunResult,
    MinecraftTaskSpec,
    MinecraftWorkloadFailure,
    MinecraftWorkloadDiagnosticsPort,
    MinecraftWorkloadEnvironmentPort,
    MinecraftWorkloadRunner,
    MinecraftCognitionCheckpointPort,
    MinecraftCognitionFactoryPort,
)
from research_platform.environment.minecraft.api import MinecraftWorldBranch


class MinecraftWorkloadBindingCloseError(RuntimeError):
    """The injected branch workload binding could not close cleanly."""


class MinecraftWorkloadBindingPort(Protocol):
    workload_id: str
    environment_generation: str
    task_manifest_digest: str
    context: ExecutionContext
    tasks: tuple[MinecraftTaskSpec, ...]
    environment: MinecraftWorkloadEnvironmentPort
    method: MethodSession
    evidence: MinecraftEvidencePort
    diagnostics: MinecraftWorkloadDiagnosticsPort | None
    cognition_factory: MinecraftCognitionFactoryPort | None
    cognition_checkpoints: MinecraftCognitionCheckpointPort | None
    branch_writes: tuple[str, ...]
    lifetime_writes: tuple[str, ...]
    private_to_method_flows: tuple[str, ...]
    def planner_for(self, task: MinecraftTaskSpec) -> MinecraftPlannerPort: ...

    def record_result(
        self,
        *,
        task: MinecraftTaskSpec,
        result: MinecraftTaskRunResult,
        context: ExecutionContext,
    ) -> None: ...

    def close(self) -> None: ...


class MinecraftWorkloadBindingFactoryPort(Protocol):
    def open(
        self,
        *,
        role: BranchRole,
        candidate: CandidateArchitecture | None,
        branch: MinecraftWorldBranch,
        variant_binding: VariantBinding | None = None,
    ) -> MinecraftWorkloadBindingPort: ...


@dataclass(frozen=True, slots=True)
class MinecraftWorkloadBatchResult:
    task_results: tuple[MinecraftTaskRunResult, ...]

    @property
    def success_rate(self) -> float:
        return sum(result.success for result in self.task_results) / max(1, len(self.task_results))

    @property
    def utility_mean(self) -> float:
        return sum(result.utility for result in self.task_results) / max(1, len(self.task_results))

    @property
    def total_steps(self) -> int:
        return sum(result.steps for result in self.task_results)

    @property
    def total_duration_s(self) -> float:
        return sum(result.duration_s for result in self.task_results)

    @property
    def memory_queries(self) -> int:
        return sum(result.memory_queries for result in self.task_results)

    @property
    def blocked_count(self) -> int:
        return sum(result.blocked for result in self.task_results)

    @property
    def failed_count(self) -> int:
        return sum(not result.success and not result.blocked for result in self.task_results)


class _MinecraftBatchBinding(WorkloadBatchBindingPort):
    def __init__(self, source: MinecraftWorkloadBindingPort) -> None:
        self.source = source
        self.context = source.context
        self.tasks = tuple(task.as_experiment_task() for task in source.tasks)
        self._tasks = {task.task_id: task for task in source.tasks}

    def runner_for(self, task: ExperimentTaskSpec) -> "_MinecraftTaskRunnerAdapter":
        return _MinecraftTaskRunnerAdapter(
            runner=MinecraftWorkloadRunner(
                environment=self.source.environment,
                method=self.source.method,
                evidence=self.source.evidence,
                planner=self.source.planner_for(self._tasks[task.task_id]),
                diagnostics=self.source.diagnostics,
                cognition_factory=getattr(self.source, "cognition_factory", None),
                cognition_checkpoints=getattr(self.source, "cognition_checkpoints", None),
            ),
            source_task=self._tasks[task.task_id],
        )

    def record_result(
        self,
        *,
        task: ExperimentTaskSpec,
        result: WorkloadTaskResult,
        context: ExecutionContext,
    ) -> None:
        source_task = self._tasks[task.task_id]
        self.source.record_result(
            task=source_task,
            result=MinecraftTaskRunResult(
                task_id=result.task_id,
                family=result.family,
                lineage_id=result.lineage_id,
                success=result.success,
                utility=result.utility,
                steps=result.steps,
                duration_s=result.duration_s,
                failure_reason=result.failure_reason,
                memory_queries=result.memory_queries,
                planner_actions=result.planner_actions,
                decision_cycles=result.decision_cycles,
                completion_receipt=result.completion_receipt,
                blocked=result.blocked,
                failure_scope=result.failure_scope,
                diagnostics=result.diagnostics,
            ),
            context=context,
        )

    def close(self) -> None:
        self.source.close()


class _MinecraftTaskRunnerAdapter:
    def __init__(self, *, runner: MinecraftWorkloadRunner, source_task: MinecraftTaskSpec) -> None:
        self._runner = runner
        self._source_task = source_task

    def run(self, task: ExperimentTaskSpec, context: ExecutionContext) -> WorkloadTaskResult:
        result = self._runner.run(self._source_task, context)
        return WorkloadTaskResult(
            task_id=result.task_id,
            family=result.family,
            lineage_id=result.lineage_id,
            success=result.success,
            utility=result.utility,
            steps=result.steps,
            duration_s=result.duration_s,
            failure_reason=result.failure_reason,
            memory_queries=result.memory_queries,
            planner_actions=result.planner_actions,
            decision_cycles=result.decision_cycles,
            completion_receipt=result.completion_receipt,
            blocked=result.blocked,
            failure_scope=result.failure_scope,
            diagnostics=result.diagnostics,
        )


class MinecraftWorkloadBranchExecutor(MinecraftBranchExecutorPort):
    """Execute a branch through the platform-owned generic batch executor."""

    def __init__(
        self,
        bindings: MinecraftWorkloadBindingFactoryPort,
        checkpoint_coordinator: WorkloadCheckpointCoordinatorPort | None = None,
        checkpoint_executor: WorkloadCheckpointedBatchExecutorPort | None = None,
        resume_checkpoints: Mapping[str, str] | None = None,
    ) -> None:
        self.bindings = bindings
        self.checkpoint_coordinator = checkpoint_coordinator
        self.checkpoint_executor = checkpoint_executor
        if (checkpoint_coordinator is None) != (checkpoint_executor is None):
            raise ValueError(
                "workload checkpoint coordinator and executor must be configured together"
            )
        normalized_resume = dict(resume_checkpoints or {})
        if any(
            not isinstance(branch_id, str)
            or not branch_id.strip()
            or not isinstance(checkpoint_id, str)
            or not checkpoint_id.strip()
            for branch_id, checkpoint_id in normalized_resume.items()
        ):
            raise ValueError("workload resume checkpoint identities must be non-empty")
        if normalized_resume and checkpoint_executor is None:
            raise ValueError("workload resume checkpoints require a checkpoint executor")
        self.resume_checkpoints = MappingProxyType(normalized_resume)
        self.latest_checkpoint_ids: dict[str, str] = {}

    def execute(
        self,
        *,
        role: BranchRole,
        candidate: CandidateArchitecture | None,
        branch: MinecraftWorldBranch,
        variant_binding: VariantBinding | None = None,
    ) -> MinecraftBranchExecutionResult:
        if variant_binding is None:
            # Keep the narrow legacy plumbing port usable for non-compiled
            # smoke fixtures; compiled scientific arms always take the typed
            # binding path below.
            binding = self.bindings.open(
                role=role,
                candidate=candidate,
                branch=branch,
            )
        else:
            binding = self.bindings.open(
                role=role,
                candidate=candidate,
                branch=branch,
                variant_binding=variant_binding,
            )
        batch_binding = _MinecraftBatchBinding(binding)
        if self.checkpoint_coordinator is None:
            batch_result = GenericWorkloadBatchExecutor().execute(batch_binding)
        else:
            if not isinstance(binding, WorkloadCheckpointBindingPort):
                try:
                    binding.close()
                finally:
                    raise TypeError(
                        "checkpoint-enabled Minecraft workload binding must implement "
                        "WorkloadCheckpointBindingPort"
                    )
            checkpoint_executor = self.checkpoint_executor
            if checkpoint_executor is None:
                try:
                    binding.close()
                finally:
                    raise RuntimeError("checkpoint executor invariant violated")
            checkpoint_result = checkpoint_executor.execute(
                batch_binding,
                checkpoint_binding=binding,
                resume_checkpoint_id=self.resume_checkpoints.get(branch.branch_id),
            )
            batch_result = checkpoint_result.batch
            effective_checkpoint_id = (
                checkpoint_result.latest_checkpoint_id
                or checkpoint_result.resumed_from_checkpoint_id
            )
            if effective_checkpoint_id is not None:
                self.latest_checkpoint_ids[branch.branch_id] = (
                    effective_checkpoint_id
                )
        batch = MinecraftWorkloadBatchResult(
            tuple(
                MinecraftTaskRunResult(
                    task_id=result.task_id,
                    family=result.family,
                    lineage_id=result.lineage_id,
                    success=result.success,
                    utility=result.utility,
                    steps=result.steps,
                    duration_s=result.duration_s,
                    failure_reason=result.failure_reason,
                    memory_queries=result.memory_queries,
                    planner_actions=result.planner_actions,
                    decision_cycles=result.decision_cycles,
                    completion_receipt=result.completion_receipt,
                    blocked=result.blocked,
                    failure_scope=result.failure_scope,
                    diagnostics=result.diagnostics,
                )
                for result in batch_result.task_results
            )
        )
        metrics = (
            ("task_count", float(len(batch.task_results))),
            ("success_rate", batch.success_rate),
            ("utility_mean", batch.utility_mean),
            ("steps_total", float(batch.total_steps)),
            ("duration_s_total", batch.total_duration_s),
            ("memory_queries_total", float(batch.memory_queries)),
            ("task_blocked_total", float(batch.blocked_count)),
            ("task_failed_total", float(batch.failed_count)),
            ("audit_evidence_total", float(len(getattr(binding, "audit_rows", ())))),
            ("eval_evidence_total", float(len(getattr(binding, "eval_rows", ())))),
        ) + tuple(
            metric
            for index, task_result in enumerate(batch.task_results)
            for metric in (
                (f"task.success.{index:03d}", float(task_result.success)),
                (f"task.utility.{index:03d}", float(task_result.utility)),
                (f"task.steps.{index:03d}", float(task_result.steps)),
                (f"task.duration_s.{index:03d}", float(task_result.duration_s)),
                (f"task.memory_queries.{index:03d}", float(task_result.memory_queries)),
            )
        )
        if any(not math.isfinite(value) for _, value in metrics):
            raise ValueError("Minecraft workload batch produced a non-finite metric")
        return MinecraftBranchExecutionResult(
            workload_id=binding.workload_id,
            environment_generation=binding.environment_generation,
            task_manifest_digest=binding.task_manifest_digest,
            metrics=metrics,
            branch_writes=binding.branch_writes,
            lifetime_writes=binding.lifetime_writes,
            private_to_method_flows=binding.private_to_method_flows,
        )


__all__ = [
    "MinecraftWorkloadBatchResult",
    "MinecraftWorkloadBindingCloseError",
    "MinecraftWorkloadBindingFactoryPort",
    "MinecraftWorkloadBindingPort",
    "MinecraftWorkloadBranchExecutor",
]
