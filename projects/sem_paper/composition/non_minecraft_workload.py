from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Protocol

from research_platform.environment.api import ActionRequest, ActionResult, EnvironmentSession, Observation
from research_platform.experimentation.experiment.api import ExperimentTaskSpec, FailureScope
from research_platform.experimentation.run.api import ExperimentRunSpec, RunDiagnosticsPort
from research_platform.experimentation.run.api import ExperimentRunExecutionPort
from research_platform.experimentation.study.api import (
    BoundStudyUnitExecutionPort,
    ExperimentPlan,
    StudyAssignment,
    StudyExecutionUnit,
    StudyMatrixExecutionReport,
    StudyMetricObservation,
    StudyProtocol,
    StudyUnitExecutionPort,
    VariantKind,
    VariantBinding,
)
from research_platform.experimentation.workload import (
    GenericWorkloadBatchExecutor,
    GenericWorkloadTaskRunner,
    WorkloadBatchBindingPort,
    WorkloadBatchResult,
    WorkloadCompletionPort,
    WorkloadEvidencePort,
    WorkloadFailurePolicyPort,
    WorkloadPlannerPort,
    WorkloadStatePort,
    WorkloadTaskResult,
)
from research_platform.participant.method.api import MethodObservationSink, MethodSession, MethodServices
from research_platform.platform.kernel import ExecutionContext, JsonValue, canonical_digest

from projects.sem_paper.method.self_evolving_memory.evolution import BranchRole, CandidateArchitecture

from .candidate_method import (
    CandidateArchitectureResolverPort,
    CandidateMethodMaterializerPort,
    build_candidate_resolver,
    is_fixed_provider,
)
from .project import SemPaperProjectComposition
from .study_execution import (
    _paired_assignments,
    SemPaperStudyUnitError,
)


class NonMinecraftEnvironmentFactoryPort(Protocol):
    """Project adapter for a closed-world/non-Minecraft environment."""

    def open(
        self,
        *,
        role: BranchRole,
        candidate: CandidateArchitecture | None,
        unit: StudyExecutionUnit,
        assignment: StudyAssignment,
        context: ExecutionContext,
    ) -> EnvironmentSession: ...


class NonMinecraftPlannerFactoryPort(Protocol):
    def create(
        self,
        *,
        role: BranchRole,
        candidate: CandidateArchitecture | None,
        unit: StudyExecutionUnit,
        assignment: StudyAssignment,
        task: ExperimentTaskSpec,
        method: MethodSession,
    ) -> WorkloadPlannerPort: ...


class NonMinecraftStatePort(Protocol):
    def state(self, observation: Observation) -> Mapping[str, JsonValue]: ...


class NonMinecraftEvidencePort(Protocol):
    def ingest_observation(
        self,
        observation: Observation,
        context: ExecutionContext,
    ) -> tuple[str, ...]: ...


class NonMinecraftEvidenceFactoryPort(Protocol):
    """Bind branch-local SEM evidence admission after its method is opened."""

    def create(
        self,
        *,
        role: BranchRole,
        candidate: CandidateArchitecture | None,
        unit: StudyExecutionUnit,
        assignment: StudyAssignment,
        method: MethodSession,
    ) -> NonMinecraftEvidencePort: ...


class NonMinecraftResultSinkPort(Protocol):
    def record(
        self,
        *,
        task: ExperimentTaskSpec,
        result: WorkloadTaskResult,
        context: ExecutionContext,
    ) -> None: ...


class NonMinecraftMethodObservationSinkFactoryPort(Protocol):
    def create(
        self,
        *,
        role: BranchRole,
        repetition: int,
        variant_id: str | None = None,
    ) -> MethodObservationSink: ...


@dataclass(frozen=True, slots=True)
class SemPaperNonMinecraftWorkloadPorts:
    """All non-MC adapters required by the reusable Paper workload root."""

    environment_factory: NonMinecraftEnvironmentFactoryPort
    planner_factory: NonMinecraftPlannerFactoryPort
    state: NonMinecraftStatePort
    completion: WorkloadCompletionPort
    evidence_factory: NonMinecraftEvidenceFactoryPort
    observation_sink_factory: NonMinecraftMethodObservationSinkFactoryPort
    diagnostics: RunDiagnosticsPort | None = None
    failure_policy: WorkloadFailurePolicyPort | None = None
    result_sink: NonMinecraftResultSinkPort | None = None


class NonMinecraftWorkloadCloseError(RuntimeError):
    """The non-MC adapter could not close all owned session resources."""


class NonMinecraftWorkloadOpenError(RuntimeError):
    """The non-MC adapter failed to open and clean up its branch resources."""

    def __init__(
        self,
        cause: BaseException,
        cleanup_errors: tuple[BaseException, ...] = (),
    ) -> None:
        super().__init__(
            "non-MC workload open failed"
            + (f" with {len(cleanup_errors)} cleanup error(s)" if cleanup_errors else "")
        )
        self.cause = cause
        self.cleanup_errors = cleanup_errors


class _ClosedWorldFailurePolicy(WorkloadFailurePolicyPort):
    """Default policy for a stateful environment: execution faults invalidate a branch."""

    def scope(self, phase: str, exception: BaseException) -> FailureScope:
        del phase, exception
        return FailureScope.BRANCH


class SemPaperNonMinecraftWorkloadBinding(WorkloadBatchBindingPort):
    """Paper adapter over the same platform workload batch as Minecraft.

    No closed-world state, action vocabulary, completion rule, or evidence
    schema is implemented here.  Each is supplied through a typed adapter.
    """

    def __init__(
        self,
        *,
        composition: SemPaperProjectComposition,
        environment_factory: NonMinecraftEnvironmentFactoryPort,
        planner_factory: NonMinecraftPlannerFactoryPort,
        state: NonMinecraftStatePort,
        completion: WorkloadCompletionPort,
        evidence_factory: NonMinecraftEvidenceFactoryPort,
        tasks: tuple[ExperimentTaskSpec, ...],
        study_protocol: StudyProtocol,
        unit: StudyExecutionUnit,
        study_assignment: StudyAssignment,
        context: ExecutionContext,
        observation_sink: MethodObservationSink,
        diagnostics: RunDiagnosticsPort | None = None,
        failure_policy: WorkloadFailurePolicyPort | None = None,
        result_sink: NonMinecraftResultSinkPort | None = None,
        role: BranchRole = BranchRole.CONTROL,
        candidate: CandidateArchitecture | None = None,
        variant_binding: VariantBinding | None = None,
    ) -> None:
        if not tasks:
            raise ValueError("non-MC workload requires a non-empty task manifest")
        if role is BranchRole.CONTROL and candidate is not None:
            raise ValueError("non-MC control binding cannot receive a candidate")
        if role is BranchRole.CANDIDATE and candidate is None:
            raise ValueError("non-MC candidate binding requires a candidate")
        if study_assignment.study_id != study_protocol.study_id:
            raise ValueError("non-MC study assignment belongs to another study")
        if variant_binding is None:
            expected_kind = VariantKind.CONTROL if role is BranchRole.CONTROL else VariantKind.TREATMENT
            expected_variants = tuple(
                item.variant_id for item in study_protocol.variants if item.kind is expected_kind
            )
            if len(expected_variants) != 1:
                raise ValueError(
                    f"non-MC study protocol must expose exactly one {expected_kind.value} variant"
                )
            expected_variant = expected_variants[0]
            if study_assignment.variant_id != expected_variant:
                raise ValueError(
                    f"non-MC role {role.value} requires study variant {expected_variant!r}"
                )
        elif variant_binding.variant.variant_id != study_assignment.variant_id:
            raise ValueError("non-MC compiled binding does not match the assignment")
        if study_assignment.variant_id not in {item.variant_id for item in study_protocol.variants}:
            raise ValueError("non-MC study assignment references an undeclared variant")
        self.tasks = tasks
        self.study_protocol = study_protocol
        self.study_unit = unit
        self.study_assignment = study_assignment
        self.context = context
        self._role = role
        self._candidate = candidate
        self._variant_binding = variant_binding
        self._planner_factory = planner_factory
        self._state = state
        self._completion = completion
        self._diagnostics = diagnostics
        self._failure_policy = failure_policy or _ClosedWorldFailurePolicy()
        self._result_sink = result_sink
        if variant_binding is not None:
            expected_role = (
                BranchRole.CONTROL
                if variant_binding.variant.kind is VariantKind.CONTROL
                else BranchRole.CANDIDATE
            )
            if role is not expected_role:
                raise ValueError("non-MC role does not match compiled variant binding")
            endpoint_factory = composition.bindings.variant_method_endpoint_factory
            if endpoint_factory is None:
                raise ValueError("compiled variant binding requires a method endpoint factory")
            endpoint = endpoint_factory.endpoint_for(
                binding=variant_binding,
                candidate=None if is_fixed_provider(variant_binding.provider_id) else candidate,
            )
        elif role is BranchRole.CONTROL:
            endpoint = composition.bindings.fixed_memory
        else:
            materializer = composition.bindings.candidate_method_materializer
            if materializer is None:
                raise ValueError("non-MC candidate binding requires a candidate method materializer")
            endpoint = materializer.materialize(candidate)  # type: ignore[arg-type]
        method: MethodSession | None = None
        environment: EnvironmentSession | None = None
        try:
            method = endpoint.open_session(
                session_id=f"{context.run_id}:{role.value}:rep-{study_assignment.repetition}:method",
                services=MethodServices(observation_sink=observation_sink),
            )
            environment = environment_factory.open(
                role=role,
                candidate=candidate,
                unit=unit,
                assignment=study_assignment,
                context=context,
            )
            evidence = evidence_factory.create(
                role=role,
                candidate=candidate,
                unit=unit,
                assignment=study_assignment,
                method=method,
            )
        except BaseException as exc:
            cleanup_errors: list[BaseException] = []
            if environment is not None:
                try:
                    environment.close()
                except BaseException as cleanup_exc:
                    cleanup_errors.append(cleanup_exc)
            if method is not None:
                try:
                    method.close()
                except BaseException as cleanup_exc:
                    cleanup_errors.append(cleanup_exc)
            raise NonMinecraftWorkloadOpenError(exc, tuple(cleanup_errors)) from exc
        self._method = method
        self._environment = environment
        self._evidence = evidence
        self._closed = False

    def runner_for(self, task: ExperimentTaskSpec) -> GenericWorkloadTaskRunner:
        return GenericWorkloadTaskRunner(
            environment=self._environment,
            method=self._method,
            evidence=self._evidence,
            planner=self._planner_factory.create(
                role=self._role,
                candidate=self._candidate,
                unit=self.study_unit,
                assignment=self.study_assignment,
                task=task,
                method=self._method,
            ),
            state=self._state,
            completion=self._completion,
            failure_policy=self._failure_policy,
            diagnostics=self._diagnostics,
        )

    def record_result(
        self,
        *,
        task: ExperimentTaskSpec,
        result: WorkloadTaskResult,
        context: ExecutionContext,
    ) -> None:
        if self._result_sink is not None:
            self._result_sink.record(task=task, result=result, context=context)

    def close(self) -> None:
        if self._closed:
            return
        errors: list[BaseException] = []
        try:
            self._environment.close()
        except BaseException as exc:
            errors.append(exc)
        try:
            self._method.close()
        except BaseException as exc:
            errors.append(exc)
        if errors:
            raise NonMinecraftWorkloadCloseError(
                f"non-MC workload close failed ({len(errors)} error(s))"
            ) from errors[0]
        self._closed = True


def execute_sem_paper_non_minecraft_workload(
    binding: SemPaperNonMinecraftWorkloadBinding,
) -> WorkloadBatchResult:
    """Execute a Paper closed-world batch through the platform executor."""

    return GenericWorkloadBatchExecutor().execute(binding)


class SemPaperNonMinecraftWorkloadBindingFactory:
    """Open one typed non-MC binding for a protocol assignment."""

    def __init__(
        self,
        *,
        composition: SemPaperProjectComposition,
        ports: SemPaperNonMinecraftWorkloadPorts,
        tasks: tuple[ExperimentTaskSpec, ...],
        study_protocol: StudyProtocol,
        context: ExecutionContext,
    ) -> None:
        if not tasks:
            raise ValueError("non-MC production root requires non-empty tasks")
        if study_protocol.task_manifest_digest != canonical_digest(tasks):
            raise ValueError("non-MC study protocol task digest does not match tasks")
        self._composition = composition
        self._ports = ports
        self._tasks = tasks
        self._protocol = study_protocol
        self._context = context

    def open(
        self,
        *,
        role: BranchRole,
        candidate: CandidateArchitecture | None,
        unit: StudyExecutionUnit,
        assignment: StudyAssignment,
        variant_binding: VariantBinding | None = None,
    ) -> SemPaperNonMinecraftWorkloadBinding:
        if variant_binding is None:
            expected_kind = VariantKind.CONTROL if role is BranchRole.CONTROL else VariantKind.TREATMENT
            variants = tuple(item for item in self._protocol.variants if item.kind is expected_kind)
            if len(variants) != 1 or assignment.variant_id != variants[0].variant_id:
                raise ValueError("non-MC assignment does not uniquely bind the requested branch role")
        elif variant_binding.variant.variant_id != assignment.variant_id:
            raise ValueError("non-MC assignment does not match its compiled variant binding")
        context = replace(
            self._context,
            condition_id=role.value,
            branch_id=(
                f"{self._context.run_id}:{role.value}:rep-{assignment.repetition}:"
                f"unit-{unit.unit_digest[:16]}"
            ),
        )
        if variant_binding is None:
            observation_sink = self._ports.observation_sink_factory.create(
                role=role,
                repetition=assignment.repetition,
            )
        else:
            observation_sink = self._ports.observation_sink_factory.create(
                role=role,
                repetition=assignment.repetition,
                variant_id=variant_binding.variant.variant_id,
            )
        return SemPaperNonMinecraftWorkloadBinding(
            composition=self._composition,
            environment_factory=self._ports.environment_factory,
            planner_factory=self._ports.planner_factory,
            state=self._ports.state,
            completion=self._ports.completion,
            evidence_factory=self._ports.evidence_factory,
            tasks=self._tasks,
            study_protocol=self._protocol,
            unit=unit,
            study_assignment=assignment,
            context=context,
            observation_sink=observation_sink,
            diagnostics=self._ports.diagnostics,
            failure_policy=self._ports.failure_policy,
            result_sink=self._ports.result_sink,
            role=role,
            candidate=candidate,
            variant_binding=variant_binding,
        )


@dataclass(frozen=True, slots=True)
class SemPaperNonMinecraftStudyUnitAdapter(StudyUnitExecutionPort):
    """Run one complete SEM paired unit through the generic non-MC path."""

    protocol: StudyProtocol
    candidate: CandidateArchitecture
    binding_factory: SemPaperNonMinecraftWorkloadBindingFactory
    candidate_factory: CandidateArchitectureResolverPort | None = None

    def execute(self, unit: StudyExecutionUnit) -> tuple[StudyMetricObservation, ...]:
        control_assignment, treatment_assignment = _paired_assignments(self.protocol, unit)
        control = execute_sem_paper_non_minecraft_workload(
            self.binding_factory.open(
                unit=unit,
                role=BranchRole.CONTROL,
                candidate=None,
                assignment=control_assignment,
            )
        )
        treatment = execute_sem_paper_non_minecraft_workload(
            self.binding_factory.open(
                unit=unit,
                role=BranchRole.CANDIDATE,
                candidate=self.candidate,
                assignment=treatment_assignment,
            )
        )
        return (
            _batch_observation(control_assignment, control, self.protocol),
            _batch_observation(treatment_assignment, treatment, self.protocol),
        )

    def execute_bound(
        self,
        unit: StudyExecutionUnit,
        bindings: tuple[VariantBinding, ...],
        plan_digest: str,
    ) -> tuple[StudyMetricObservation, ...]:
        if len(plan_digest) != 64:
            raise SemPaperStudyUnitError("compiled non-MC execution requires a plan digest")
        expected_ids = {item.variant_id for item in unit.assignments}
        actual_ids = tuple(item.variant.variant_id for item in bindings)
        if set(actual_ids) != expected_ids or len(actual_ids) != len(set(actual_ids)):
            raise SemPaperStudyUnitError("compiled non-MC unit bindings do not cover the unit exactly")
        observations: list[StudyMetricObservation] = []
        for binding in bindings:
            assignment = next(
                item for item in unit.assignments
                if item.variant_id == binding.variant.variant_id
            )
            is_fixed = is_fixed_provider(binding.provider_id)
            candidate = None if is_fixed else (
                self.candidate_factory(binding)
                if self.candidate_factory is not None
                else self.candidate
            )
            role = (
                BranchRole.CONTROL
                if binding.variant.kind is VariantKind.CONTROL
                else BranchRole.CANDIDATE
            )
            batch = execute_sem_paper_non_minecraft_workload(
                self.binding_factory.open(
                    unit=unit,
                    role=role,
                    candidate=candidate,
                    assignment=assignment,
                    variant_binding=binding,
                )
            )
            observations.append(_batch_observation(assignment, batch, self.protocol))
        return tuple(observations)


def _batch_observation(
    assignment: StudyAssignment,
    result: WorkloadBatchResult,
    protocol: StudyProtocol,
) -> StudyMetricObservation:
    values = {
        "success_rate": float(result.success_rate),
        "utility_mean": float(result.utility_mean),
        "steps_total": float(result.total_steps),
        "duration_s_total": float(result.total_duration_s),
        "memory_queries_total": float(result.memory_queries),
        "task_failed_total": float(result.failed_count),
        "task_blocked_total": float(result.blocked_count),
    }
    missing = [name for name in protocol.metric_names if name not in values]
    unknown = [name for name in values if name not in protocol.metric_names]
    if missing or unknown:
        raise SemPaperStudyUnitError(
            f"non-MC study metric schema mismatch: missing={missing!r} unknown={unknown!r}"
        )
    return StudyMetricObservation(
        assignment,
        tuple((name, values[name]) for name in protocol.metric_names),
    )


@dataclass(frozen=True, slots=True)
class SemPaperNonMinecraftProductionRoot:
    """Non-MC Paper root over the same study and generic workload systems."""

    composition: SemPaperProjectComposition
    run_spec: ExperimentRunSpec
    binding_factory: SemPaperNonMinecraftWorkloadBindingFactory
    study_unit_executor: StudyUnitExecutionPort
    run_executor: ExperimentRunExecutionPort
    candidate: CandidateArchitecture
    study_protocol: StudyProtocol
    experiment_plan: ExperimentPlan | None = None

    def execute_run(self):
        """Execute every declared non-MC assignment through the run parent."""

        if self.experiment_plan is None:
            return self.run_executor.execute(
                run_spec=self.run_spec,
                protocol=self.study_protocol,
                unit_adapter=self.study_unit_executor,
            )
        return self.run_executor.execute(
            run_spec=self.run_spec,
            plan=self.experiment_plan,
            unit_adapter=self.study_unit_executor,
        )


def compose_sem_paper_non_minecraft_production_root(
    *,
    composition: SemPaperProjectComposition,
    run_spec: ExperimentRunSpec,
    ports: SemPaperNonMinecraftWorkloadPorts,
    tasks: tuple[ExperimentTaskSpec, ...],
    study_protocol: StudyProtocol,
    context: ExecutionContext,
    run_executor: ExperimentRunExecutionPort,
    candidate: CandidateArchitecture,
    experiment_plan: ExperimentPlan | None = None,
    candidate_factory: CandidateArchitectureResolverPort | None = None,
) -> SemPaperNonMinecraftProductionRoot:
    if context.run_id != run_spec.run_id:
        raise ValueError("non-MC execution context does not match run specification")
    bound_candidate_factory = build_candidate_resolver(
        fallback=candidate,
        override=candidate_factory,
    )
    binding_factory = SemPaperNonMinecraftWorkloadBindingFactory(
        composition=composition,
        ports=ports,
        tasks=tasks,
        study_protocol=study_protocol,
        context=context,
    )
    unit_executor = SemPaperNonMinecraftStudyUnitAdapter(
        protocol=study_protocol,
        candidate=candidate,
        binding_factory=binding_factory,
        candidate_factory=bound_candidate_factory,
    )
    return SemPaperNonMinecraftProductionRoot(
        composition=composition,
        run_spec=run_spec,
        binding_factory=binding_factory,
        study_unit_executor=unit_executor,
        run_executor=run_executor,
        candidate=candidate,
        study_protocol=study_protocol,
        experiment_plan=experiment_plan,
    )


__all__ = [
    "NonMinecraftEnvironmentFactoryPort",
    "NonMinecraftEvidenceFactoryPort",
    "NonMinecraftEvidencePort",
    "NonMinecraftPlannerFactoryPort",
    "NonMinecraftResultSinkPort",
    "NonMinecraftMethodObservationSinkFactoryPort",
    "NonMinecraftStatePort",
    "NonMinecraftWorkloadCloseError",
    "NonMinecraftWorkloadOpenError",
    "SemPaperNonMinecraftWorkloadBinding",
    "SemPaperNonMinecraftWorkloadBindingFactory",
    "SemPaperNonMinecraftWorkloadPorts",
    "SemPaperNonMinecraftProductionRoot",
    "SemPaperNonMinecraftStudyUnitAdapter",
    "compose_sem_paper_non_minecraft_production_root",
    "execute_sem_paper_non_minecraft_workload",
]
