from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Callable

from noetrium.contracts import (
    BasicStudyMetricAggregator,
    BoundStudyUnitExecutionPort,
    EnvironmentAssignmentIdentity,
    EnvironmentAssignmentIsolationPort,
    EnvironmentAssignmentIsolationReceipt,
    ExperimentPlan,
    StudyExecutionUnit,
    StudyMatrixExecutionReport,
    StudyMatrixExecutor,
    StudyMetricObservation,
    VariantBinding,
)

from projects.sem_paper.composition.environment import (
    RealMinecraftEnvironment,
    ScriptedMinecraftEnvironment,
)
from projects.sem_paper.method.self_evolving_memory import (
    SemMethodAgentMemoryAdapter,
    open_sem_method_session,
)


@dataclass
class SEMExperimentRunner(BoundStudyUnitExecutionPort):
    """SEM adapter at the compiled Noetrium study-plan boundary."""

    plan: ExperimentPlan
    environment: object
    assignment_isolation_factory: Callable[
        [EnvironmentAssignmentIdentity, object, VariantBinding],
        EnvironmentAssignmentIsolationPort,
    ] | None = None

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
            raise ValueError("SEM runner received a different frozen plan")
        return tuple(
            self._execute_assignment(assignment, binding)
            for assignment, binding in zip(unit.assignments, bindings, strict=True)
        )

    def _execute_assignment(
        self,
        assignment,
        binding: VariantBinding,
    ) -> StudyMetricObservation:
        treatment = binding.variant.variant_id
        session, _method_endpoint = open_sem_method_session(
            session_id=f"{assignment.variant_id}:{assignment.repetition}",
            treatment_id=treatment,
            seed=assignment.seed,
            initial_memory=(),
        )
        memory = (
            None
            if treatment == "no_memory"
            else SemMethodAgentMemoryAdapter(session)
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
                memory=memory,
            )
            diagnostics = dict(session.diagnostics())
        finally:
            if isolation is not None and isolation_receipt is not None:
                isolation.finalize_assignment(identity, isolation_receipt)
            session.close()
        self._write_raw_assignment(assignment, binding, diagnostics, results)
        count = len(results)
        if count == 0:
            raise RuntimeError("SEM environment returned no task results")
        success_count = sum(item.success for item in results)
        generation_number = int(diagnostics.get("architecture_generation", 0))
        metrics = (
            ("success_rate", success_count / count),
            ("utility_mean", sum(item.utility for item in results) / count),
            ("steps_total", float(sum(item.steps for item in results))),
            ("duration_s_total", sum(item.duration_s for item in results)),
            ("memory_queries_total", float(sum(item.memory_queries for item in results))),
            ("memory_entries_total", float(diagnostics.get("memory_entry_count", 0))),
            ("active_node_count", float(diagnostics.get("active_node_count", 0))),
            ("architecture_generation", float(generation_number)),
            ("candidate_count", float(diagnostics.get("candidate_count", 0))),
            ("adopted_count", float(diagnostics.get("adopted_count", 0))),
            ("rejected_count", float(diagnostics.get("rejected_count", 0))),
            ("historical_backfill_count", float(diagnostics.get("historical_backfill_count", 0))),
            ("verified_actions_total", float(sum(item.verified_actions for item in results))),
            ("evidence_closed_total", float(sum(item.evidence_closed for item in results))),
        )
        return StudyMetricObservation(assignment, metrics)

    @staticmethod
    def _write_raw_assignment(assignment, binding, diagnostics, results) -> None:
        root = Path(os.environ.get("SEM_RESULTS_DIR", "results/real"))
        root.mkdir(parents=True, exist_ok=True)
        payload = {
            "assignment": {
                "assignment_id": assignment.assignment_digest,
                "study_id": assignment.study_id,
                "variant_id": assignment.variant_id,
                "repetition": assignment.repetition,
                "seed": assignment.seed,
            },
            "variant": {
                "implementation_id": binding.variant.implementation_id,
                "configuration_digest": binding.variant.configuration_digest,
            },
            "diagnostics": diagnostics,
            "tasks": [
                {
                    "task_id": item.task_id,
                    "success": item.success,
                    "utility": item.utility,
                    "steps": item.steps,
                    "duration_s": item.duration_s,
                    "memory_queries": item.memory_queries,
                    "blocked": item.blocked,
                    "failure_class": item.failure_class,
                    "verified_actions": item.verified_actions,
                    "evidence_closed": item.evidence_closed,
                    "outcome_codes": list(item.outcome_codes),
                    "evidence_digest": item.evidence_digest,
                }
                for item in results
            ],
        }
        target = root / f"{assignment.assignment_digest}.json"
        target.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2), encoding="utf-8")


def _plan(repetitions: int | None = None) -> ExperimentPlan:
    from projects.sem_paper.experiments.protocol import (
        build_sem_paper_confirmatory_protocol,
        compile_sem_paper_experiment_plan,
    )
    protocol = build_sem_paper_confirmatory_protocol(
        repetitions=(
            repetitions
            if repetitions is not None
            else int(os.environ.get("SEM_REPETITIONS", "3"))
        )
    )
    return compile_sem_paper_experiment_plan(protocol)


def run_confirmatory_smoke() -> StudyMatrixExecutionReport:
    return SEMExperimentRunner(_plan(), ScriptedMinecraftEnvironment()).run()


def run_real_matrix(repetitions: int | None = None) -> StudyMatrixExecutionReport:
    plan = _plan(repetitions)
    return SEMExperimentRunner(plan, RealMinecraftEnvironment()).run()


def run_real_pilot():
    plan = _plan(1)
    runner = SEMExperimentRunner(plan, RealMinecraftEnvironment())
    assignment = plan.assignments[0]
    observation = runner._execute_assignment(
        assignment, plan.binding_for(assignment.variant_id)
    )
    return plan, observation


__all__ = [
    "SEMExperimentRunner",
    "run_confirmatory_smoke",
    "run_real_matrix",
    "run_real_pilot",
]
