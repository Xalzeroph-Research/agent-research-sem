from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from noetrium.contracts import (
    BasicStudyMetricAggregator,
    EnvironmentAssignmentIdentity,
    EnvironmentAssignmentIsolationPort,
    EnvironmentAssignmentIsolationReceipt,
    BoundStudyUnitExecutionPort,
    ExperimentPlan,
    StudyExecutionUnit,
    StudyMatrixExecutionReport,
    StudyMatrixExecutor,
    StudyMetricObservation,
    VariantBinding,
)
# StudyMatrixExecutor is a stable Noetrium contract export.

from projects.sem_paper.composition.environment import (
    RealMinecraftEnvironment,
    ScriptedMinecraftEnvironment,
)
from projects.sem_paper.method.self_evolving_memory import SEMMethodSession


@dataclass
class SEMExperimentRunner(BoundStudyUnitExecutionPort):
    """SEM-owned adapter at Noetrium's compiled-plan boundary."""

    plan: ExperimentPlan
    environment: object
    assignment_isolation_factory: Callable[[EnvironmentAssignmentIdentity, object, VariantBinding], EnvironmentAssignmentIsolationPort] | None = None

    def run(self, assignments=None) -> StudyMatrixExecutionReport:
        executor = StudyMatrixExecutor(BasicStudyMetricAggregator())
        selected = self.plan.assignments if assignments is None else tuple(assignments)
        return executor.execute_plan(self.plan, selected, self)

    def execute_bound(
        self,
        unit: StudyExecutionUnit,
        bindings: tuple[VariantBinding, ...],
        plan_digest: str,
    ) -> tuple[StudyMetricObservation, ...]:
        if plan_digest != self.plan.plan_digest:
            raise ValueError("SEM runner received a plan digest different from its frozen plan")
        return tuple(
            self._execute_assignment(assignment, binding)
            for assignment, binding in zip(unit.assignments, bindings, strict=True)
        )

    def _execute_assignment(
        self,
        assignment,
        binding: VariantBinding,
    ) -> StudyMetricObservation:
        implementation = binding.variant.implementation_id.rsplit(".", 1)[-1]
        treatment = implementation
        session = SEMMethodSession(
            session_id=f"{assignment.variant_id}:{assignment.repetition}",
            treatment_id=treatment,
            seed=assignment.seed,
            adaptive=treatment != "fixed_memory",
            initial_memory=(f"seed={assignment.seed}",),
        )
        isolation = None
        isolation_receipt: EnvironmentAssignmentIsolationReceipt | None = None
        if self.assignment_isolation_factory is not None:
            identity = EnvironmentAssignmentIdentity(
                assignment_id=assignment.assignment_digest,
                study_id=assignment.study_id,
                plan_digest=self.plan.plan_digest,
                variant_id=assignment.variant_id,
                repetition=assignment.repetition,
                seed=assignment.seed,
                environment_id=str(getattr(self.environment, "environment_id", "unknown")),
            )
            isolation = self.assignment_isolation_factory(identity, assignment, binding)
            isolation_receipt = isolation.prepare_assignment(identity)
        try:
            results = self.environment.run_suite(
                session=session,
                variant_id=assignment.variant_id,
                seed=assignment.seed,
                assignment=assignment,
                assignment_isolation=isolation,
            )
        finally:
            if isolation is not None and isolation_receipt is not None:
                isolation.finalize_assignment(identity, isolation_receipt)
            session.close()
        count = len(results)
        success_count = sum(item.success for item in results)
        return StudyMetricObservation(
            assignment,
            (
                ("success_rate", success_count / count),
                ("utility_mean", sum(item.utility for item in results) / count),
                ("steps_total", float(sum(item.steps for item in results))),
                ("duration_s_total", sum(item.duration_s for item in results)),
                ("memory_queries_total", float(sum(item.memory_queries for item in results))),
                ("task_failed_total", float(count - success_count)),
                ("task_blocked_total", float(sum(item.blocked for item in results))),
                ("task_precondition_failed_total", float(sum(item.failure_class == "precondition_missing" for item in results))),
                ("task_partial_total", float(sum(item.failure_class in {"partial_effect", "path_interrupted"} for item in results))),
                ("task_no_threats_total", float(sum(item.failure_class == "no_threats" for item in results))),
                ("verified_actions_total", float(sum(item.verified_actions for item in results))),
                ("evidence_closed_total", float(sum(item.evidence_closed for item in results))),
            ),
        )


def run_confirmatory_smoke() -> StudyMatrixExecutionReport:
    from projects.sem_paper.experiments.protocol import compile_sem_paper_experiment_plan

    plan = compile_sem_paper_experiment_plan()
    return SEMExperimentRunner(plan, ScriptedMinecraftEnvironment()).run()


def run_real_matrix() -> StudyMatrixExecutionReport:
    from projects.sem_paper.experiments.protocol import compile_sem_paper_experiment_plan

    plan = compile_sem_paper_experiment_plan()
    return SEMExperimentRunner(plan, RealMinecraftEnvironment()).run()


def run_real_pilot():
    from projects.sem_paper.experiments.protocol import compile_sem_paper_experiment_plan

    plan = compile_sem_paper_experiment_plan()
    runner = SEMExperimentRunner(plan, RealMinecraftEnvironment())
    assignment = plan.assignments[0]
    observation = runner._execute_assignment(
        assignment, plan.binding_for(assignment.variant_id)
    )
    return plan, observation


__all__ = ["SEMExperimentRunner", "run_confirmatory_smoke", "run_real_matrix", "run_real_pilot"]