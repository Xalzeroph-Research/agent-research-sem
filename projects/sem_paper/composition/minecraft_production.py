from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from research_platform.environment.minecraft.api import (
    MinecraftWorldBranch,
    MinecraftWorldCut,
    MinecraftWorldCutPort,
)
from research_platform.platform.kernel import ExecutionContext
from research_platform.experimentation.run.api import RunArtifactStorePort
from research_platform.experimentation.checkpoint.api import (
    WorkloadCheckpointCoordinatorPort,
    WorkloadCheckpointedBatchExecutorPort,
)
from research_platform.experimentation.run.api import ExperimentRunExecutionPort, ExperimentRunSpec
from research_platform.experimentation.study.api import (
    StudyMatrixExecutionReport,
    BoundStudyUnitExecutionPort,
    ExperimentPlan,
    StudyProtocol,
    StudyUnitExecutionPort,
)

from projects.sem_paper.method.self_evolving_memory.evolution import (
    BranchRole,
    CandidateArchitecture,
)

from .minecraft_binding import (
    SemPaperBranchRuntimeRequestFactoryPort,
    SemPaperMethodObservationSinkFactoryPort,
    SemPaperMinecraftWorkloadBindingFactory,
    SemPaperPlannerFactoryPort,
)
from .candidate_method import (
    CandidateArchitectureResolverPort,
    build_candidate_resolver,
    validate_plan_provider_closure,
)
from .minecraft_workload import (
    MinecraftCognitionFactoryPort,
    MinecraftTaskSpec,
    MinecraftWorkloadDiagnosticsPort,
    minecraft_task_manifest_digest,
)
from .minecraft_workload_executor import MinecraftWorkloadBranchExecutor
from .project import SemPaperProjectComposition
from .study_execution import (
    MinecraftSourceCutPublicationPort,
    SemPaperMinecraftStudyUnitAdapter,
)
from .study import compile_sem_paper_experiment_plan


@dataclass(frozen=True, slots=True)
class SemPaperMinecraftProductionRoot:
    """Frozen Paper production graph; no live resource is opened here."""

    composition: SemPaperProjectComposition
    run_spec: ExperimentRunSpec
    workload_bindings: SemPaperMinecraftWorkloadBindingFactory
    workload_executor: MinecraftWorkloadBranchExecutor
    study_unit_executor: BoundStudyUnitExecutionPort
    run_executor: ExperimentRunExecutionPort
    candidate: CandidateArchitecture
    study_protocol: StudyProtocol
    plan: ExperimentPlan

    def execute_run(self):
        """Delegate the run to the platform run parent."""

        return self.run_executor.execute(
            run_spec=self.run_spec,
            plan=self.plan,
            unit_adapter=self.study_unit_executor,
        )


def compose_sem_paper_minecraft_production_root(
    *,
    composition: SemPaperProjectComposition,
    run_spec: ExperimentRunSpec,
    world_cuts: MinecraftWorldCutPort,
    branch_runtime_factory,
    request_factory: SemPaperBranchRuntimeRequestFactoryPort,
    planner_factory: SemPaperPlannerFactoryPort,
    observation_sink_factory: SemPaperMethodObservationSinkFactoryPort,
    tasks: tuple[MinecraftTaskSpec, ...],
    context: ExecutionContext,
    workload_id_factory: Callable[[BranchRole, MinecraftWorldBranch], str],
    session_id: str,
    branch_id_factory: Callable[[BranchRole, int], str],
    destination_factory: Callable[[str], str],
    diagnostics: MinecraftWorkloadDiagnosticsPort | None = None,
    artifact_store: RunArtifactStorePort | None = None,
    cognition_factory: MinecraftCognitionFactoryPort | None = None,
    checkpoint_coordinator: WorkloadCheckpointCoordinatorPort | None = None,
    checkpoint_executor: WorkloadCheckpointedBatchExecutorPort | None = None,
    resume_checkpoints: Mapping[str, str] | None = None,
    source_cuts: Mapping[int, MinecraftWorldCut] | None = None,
    source_cut_publication: MinecraftSourceCutPublicationPort | None = None,
    study_protocol: StudyProtocol,
    plan: ExperimentPlan | None = None,
    run_executor: ExperimentRunExecutionPort,
    candidate: CandidateArchitecture,
    candidate_factory: CandidateArchitectureResolverPort | None = None,
) -> SemPaperMinecraftProductionRoot:
    """Freeze the sole project-to-Minecraft paired-evaluation composition graph."""

    if study_protocol.task_manifest_digest != minecraft_task_manifest_digest(tasks):
        raise ValueError("study protocol task manifest digest does not match workload tasks")
    compiled_plan = plan or compile_sem_paper_experiment_plan(study_protocol)
    compiled_plan.assert_consistent()
    if compiled_plan.protocol != study_protocol:
        raise ValueError("Minecraft production plan is not compiled from the supplied protocol")
    if context.run_id != run_spec.run_id:
        raise ValueError("Paper MC execution context does not match run specification")
    bound_candidate_factory = build_candidate_resolver(
        fallback=candidate,
        override=candidate_factory,
    )
    variant_factory = getattr(
        composition.bindings, "variant_method_endpoint_factory", None
    )
    scientific_sem_plan = any(
        binding.provider_id.startswith("sem-paper.")
        for binding in compiled_plan.bindings
    )
    if scientific_sem_plan:
        if variant_factory is None:
            raise ValueError("Minecraft production plan requires a variant endpoint factory")
        validate_plan_provider_closure(
            plan=compiled_plan,
            factory=variant_factory,
            candidate=candidate,
            candidate_factory=bound_candidate_factory,
        )
    bindings = SemPaperMinecraftWorkloadBindingFactory(
        composition=composition,
        branch_runtime_factory=branch_runtime_factory,
        request_factory=request_factory,
        planner_factory=planner_factory,
        observation_sink_factory=observation_sink_factory,
        tasks=tasks,
        context=context,
        workload_id_factory=workload_id_factory,
        diagnostics=diagnostics,
        artifact_store=artifact_store,
        cognition_factory=cognition_factory,
    )
    executor = MinecraftWorkloadBranchExecutor(
        bindings,
        checkpoint_coordinator,
        checkpoint_executor,
        resume_checkpoints,
    )
    unit_executor = SemPaperMinecraftStudyUnitAdapter(
        protocol=study_protocol,
        candidate=candidate,
        world_cuts=world_cuts,
        workload_executor=executor,
        session_id=session_id,
        context=context,
        branch_id_factory=branch_id_factory,
        destination_factory=destination_factory,
        source_cuts=dict(source_cuts or {}),
        source_cut_publication=source_cut_publication,
        candidate_factory=bound_candidate_factory,
    )
    return SemPaperMinecraftProductionRoot(
        composition=composition,
        run_spec=run_spec,
        workload_bindings=bindings,
        workload_executor=executor,
        study_unit_executor=unit_executor,
        run_executor=run_executor,
        candidate=candidate,
        study_protocol=study_protocol,
        plan=compiled_plan,
    )


__all__ = [
    "SemPaperMinecraftProductionRoot",
    "compose_sem_paper_minecraft_production_root",
]
