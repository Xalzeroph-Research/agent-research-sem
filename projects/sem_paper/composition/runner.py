from __future__ import annotations

from dataclasses import dataclass
import base64
import os
from pathlib import Path
from typing import Callable
from uuid import uuid4

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
    canonical_digest,
)
from noetrium.contracts.systems.experimentation__run import RunArtifactKind
from noetrium.platform import bind_directory_run_artifact_store

from projects.sem_paper.composition.environment import (
    RealMinecraftEnvironment,
    ScriptedMinecraftEnvironment,
)
from projects.sem_paper.method.self_evolving_memory import (
    SemMethodAgentMemoryAdapter,
    open_sem_method_session,
)


_DEFAULT_EXECUTION_RUN_ID = uuid4().hex


def _execution_run_id() -> str:
    return os.environ.get("SEM_EXECUTION_RUN_ID", "").strip() or _DEFAULT_EXECUTION_RUN_ID


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
            method_snapshot = session.checkpoint()
            environment_checkpoint = getattr(self.environment, "last_checkpoint", None)
        finally:
            if isolation is not None and isolation_receipt is not None:
                isolation.finalize_assignment(identity, isolation_receipt)
            session.close()
        self._write_raw_assignment(
            assignment,
            binding,
            diagnostics,
            results,
            method_snapshot=method_snapshot,
            environment_checkpoint=environment_checkpoint,
        )
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

    def _write_raw_assignment(
        self,
        assignment,
        binding,
        diagnostics,
        results,
        *,
        method_snapshot,
        environment_checkpoint: bytes | None,
    ) -> None:
        execution_run_id = (
            os.environ.get("SEM_EXECUTION_RUN_ID", "").strip()
            or getattr(self.environment, "execution_run_id", "")
            or _DEFAULT_EXECUTION_RUN_ID
        )
        root = (
            Path(os.environ.get("SEM_RESULTS_DIR", "results/real"))
            / execution_run_id
        )
        run_id = f"{execution_run_id}-{assignment.assignment_digest}"
        payload = {
            "execution_run_id": execution_run_id,
            "environment_id": str(getattr(self.environment, "environment_id", "unknown")),
            "world_reset_per_assignment": (
                os.environ.get("MC_REQUIRE_WORLD_RESET") == "1"
                and bool(os.environ.get("MC_ASSIGNMENT_RESET_COMMAND", "").strip())
            ),
            "planner_mode": os.environ.get("SEM_PLANNER_MODE", "model"),
            "qualified_model_bound": bool(
                os.environ.get("SEM_MODEL_QUALIFIED_CLOSURE", "").strip()
            ),
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
            "checkpoints": {
                "method": {
                    "schema_version": method_snapshot.schema_version,
                    "method_id": method_snapshot.method_id,
                    "implementation_version": method_snapshot.implementation_version,
                    "session_id": method_snapshot.session_id,
                    "payload_sha256": method_snapshot.payload_sha256,
                    "opaque_payload_b64": base64.b64encode(
                        method_snapshot.opaque_payload
                    ).decode("ascii"),
                },
                "environment": (
                    {
                        "payload_b64": base64.b64encode(
                            environment_checkpoint
                        ).decode("ascii"),
                        "payload_sha256": canonical_digest(
                            {"payload": environment_checkpoint.hex()}
                        ),
                    }
                    if environment_checkpoint is not None
                    else None
                ),
            },
            "logs": {
                "episode": [
                    {
                        "episode_id": f"{assignment.assignment_digest}:{item.task_id}",
                        "task_id": item.task_id,
                        "world_id": str(getattr(
                            getattr(self.environment, "identity", None),
                            "artifact_digest", "unknown",
                        )),
                        "method": binding.variant.variant_id,
                        "success": int(item.success),
                        "progress": 1.0 if item.success else 0.0,
                        "total_steps": item.steps,
                        "llm_calls": 1 if os.environ.get(
                            "SEM_PLANNER_MODE", "model"
                        ) == "model" else 0,
                        "memory_calls": item.memory_queries,
                        "evolution_events": int(
                            diagnostics.get("evolution_event_count", 0)
                        ),
                        "total_cost": 0.0,
                    }
                    for item in results
                ],
                "memory_query": list(diagnostics.get("memory_query_logs", [])),
                "evolution": list(diagnostics.get("evolution_ledger", [])),
            },
            "tasks": [
                {
                    "task_id": item.task_id,
                    "family": item.family,
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
        artifact_binding = bind_directory_run_artifact_store(
            root,
            run_id=run_id,
            task_group_id=f"sem-artifacts-{run_id}",
        )
        try:
            store = artifact_binding.store
            artifact_ref = f"{assignment.assignment_digest}.json"
            store.publish_json(
                artifact_ref,
                payload,
                kind=RunArtifactKind.RESULT,
            )
            receipt = store.finalize(
                artifact_ref,
                kind=RunArtifactKind.RESULT,
                record_stream=False,
            )
            store.verify_finalized(receipt)
        finally:
            artifact_binding.close()


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
