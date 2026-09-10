from __future__ import annotations

from pathlib import Path

from noetrium.contracts.systems.model__request import ExecutionContext

from projects.sem_paper.composition.environment import EnvironmentTaskResult
from projects.sem_paper.method.self_evolving_memory.runtime import (
    SEMMethodImplementation,
    open_sem_method_session,
    run_sem_assignment_program,
)


def _result() -> EnvironmentTaskResult:
    return EnvironmentTaskResult(
        task_id="task-1",
        success=True,
        utility=1.0,
        steps=1,
        duration_s=0.1,
        memory_queries=1,
        blocked=False,
        evidence_digest="evidence-digest",
        verified_actions=1,
        evidence_closed=True,
        outcome_codes=("verified",),
        family="resource",
    )


def test_sem_assignment_is_hosted_and_resumed_by_universal_method_machine(tmp_path: Path) -> None:
    implementation = SEMMethodImplementation("sem", "seed-1")
    execution = ExecutionContext(
        "umm-sem-test-run",
        "umm-sem-trace",
        "umm-sem-span",
        study_id="sem-study",
        condition_id="sem",
    )
    session, _ = open_sem_method_session(
        session_id="umm-sem-session",
        treatment_id="sem",
        seed="seed-1",
    )
    calls: list[str] = []

    def run_environment() -> tuple[EnvironmentTaskResult, ...]:
        calls.append("environment")
        return (_result(),)

    first, first_meta = run_sem_assignment_program(
        session=session,
        implementation=implementation,
        execution=execution,
        checkpoint_root=tmp_path / "checkpoints",
        environment_run=run_environment,
        decode_result=lambda value: EnvironmentTaskResult(**value),
    )
    assert first == (_result(),)
    assert calls == ["environment"]
    assert first_meta["status"] == "succeeded"
    assert first_meta["checkpoint"] is not None

    resumed_session, _ = open_sem_method_session(
        session_id="umm-sem-session",
        treatment_id="sem",
        seed="seed-1",
    )
    resumed, resumed_meta = run_sem_assignment_program(
        session=resumed_session,
        implementation=implementation,
        execution=execution,
        checkpoint_root=tmp_path / "checkpoints",
        environment_run=lambda: (_ for _ in ()).throw(AssertionError("replayed environment")),
        decode_result=lambda value: EnvironmentTaskResult(**value),
        resume=True,
    )
    assert resumed == first
    assert resumed_meta["resumed"] is True
    assert calls == ["environment"]


