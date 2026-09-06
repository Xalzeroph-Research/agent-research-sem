from __future__ import annotations

from dataclasses import dataclass

from noetrium.contracts import (
    BasicStudyMetricAggregator,
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
        treatment = "self_evolving" if implementation in {"rule_based", "self_evolving"} else "fixed_memory"
        session = SEMMethodSession(
            session_id=f"{assignment.variant_id}:{assignment.repetition}",
            treatment_id=treatment,
            seed=assignment.seed,
            adaptive=treatment != "fixed_memory",
            initial_memory=(f"seed={assignment.seed}",),
        )
        results = self.environment.run_suite(
            session=session,
            variant_id=assignment.variant_id,
            seed=assignment.seed,
        )
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
            ),
        )


def run_confirmatory_smoke() -> StudyMatrixExecutionReport:
    from projects.sem_paper.experiments.protocol import compile_sem_paper_experiment_plan

    plan = compile_sem_paper_experiment_plan()
    return SEMExperimentRunner(plan, ScriptedMinecraftEnvironment()).run()


def run_real_pilot():
    from projects.sem_paper.experiments.protocol import compile_sem_paper_experiment_plan

    plan = compile_sem_paper_experiment_plan()
    runner = SEMExperimentRunner(plan, RealMinecraftEnvironment())
    assignment = plan.assignments[0]
    observation = runner._execute_assignment(
        assignment, plan.binding_for(assignment.variant_id)
    )
    return plan, observation


__all__ = ["SEMExperimentRunner", "run_confirmatory_smoke", "run_real_pilot"]