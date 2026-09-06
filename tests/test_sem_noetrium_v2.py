from __future__ import annotations

from projects.sem_paper.api import PROJECT_MANIFEST
from projects.sem_paper.composition import ScriptedMinecraftEnvironment
from projects.sem_paper.composition.runner import SEMExperimentRunner
from projects.sem_paper.experiments import (
    build_benchmark,
    build_sem_paper_confirmatory_protocol,
    compile_sem_paper_experiment_plan,
    is_confirmatory_protocol,
)
from projects.sem_paper.method.self_evolving_memory import (
    RuleBasedEvolver,
    SEMMethodSession,
    SemMethodAgentMemoryAdapter,
)
from projects.sem_paper.benchmarks import (
    JsonTaskBenchmarkAdapter,
    memory_agent_bench_adapter,
    minedojo_adapter,
)


def test_manifest_uses_new_project_contract() -> None:
    assert PROJECT_MANIFEST.identity.project_id == "sem-paper"
    assert len(PROJECT_MANIFEST.capability_requirements) == 3


def test_protocol_and_plan_are_complete() -> None:
    protocol = build_sem_paper_confirmatory_protocol()
    plan = compile_sem_paper_experiment_plan(protocol)
    assert is_confirmatory_protocol(protocol)
    assert len(protocol.variants) == 6
    assert len(plan.assignments) == 72
    plan.assert_consistent()


def test_method_evolves_and_restores() -> None:
    method = SEMMethodSession(
        session_id="test", treatment_id="self_evolving",
        seed="Seed-C", adaptive=True,
    )
    candidate = RuleBasedEvolver().propose("timeout", "task")
    assert candidate.status == "PROPOSED"
    method.task_completed({
        "task_id": "t1", "family": "x", "lineage_id": "t1",
        "success": False, "utility": -1, "steps": 2, "failure_reason": "timeout",
    }, None)
    snapshot = method.checkpoint()
    restored = SEMMethodSession(
        session_id="test", treatment_id="self_evolving",
        seed="Seed-C", adaptive=True,
    )
    restored.restore(snapshot)
    assert restored.generation == method.generation
    assert restored.diagnostics()["entry_count"] == method.diagnostics()["entry_count"]


def test_method_owns_real_action_plan() -> None:
    method = SEMMethodSession(
        session_id="plan", treatment_id="fixed_memory",
        seed="Seed-C", adaptive=False,
    )
    plan = method.plan_actions({"family": "combat_survival"})
    assert plan[0][0] == "defend_self"
    assert plan[0][1]["max_targets"] == 1


def test_agent_memory_adapter_keeps_method_generation() -> None:
    method = SEMMethodSession(
        session_id="agent", treatment_id="fixed_memory",
        seed="Seed-X", adaptive=False,
    )
    adapter = SemMethodAgentMemoryAdapter(method)
    assert adapter.session is method


def test_external_benchmark_metadata_adapter(tmp_path) -> None:
    source = tmp_path / "tasks.json"
    source.write_text(
        '{"tasks":[{"task_id":"m1","goal":"remember this","family":"memory"}]}',
        encoding="utf-8",
    )
    benchmark = JsonTaskBenchmarkAdapter("memory-agent-bench").build(source)
    assert benchmark.benchmark_id == "memory-agent-bench"
    assert benchmark.tasks[0].task_id == "m1"
    assert minedojo_adapter().benchmark_id == "minedojo"
    assert memory_agent_bench_adapter().benchmark_id == "memory-agent-bench"


def test_scripted_environment_is_recoverable() -> None:
    environment = ScriptedMinecraftEnvironment()
    assert environment.capabilities.supported
    session = environment.open_session(session_id="env", services=object())
    payload = session.checkpoint()
    session.restore(payload)
    session.close()


def test_smoke_report_is_complete() -> None:
    plan = compile_sem_paper_experiment_plan()
    report = SEMExperimentRunner(plan, ScriptedMinecraftEnvironment()).run()
    assert len(build_benchmark().tasks) == 6
    assert len(report.observations) == 72
    assert report.plan_digest == plan.plan_digest

def test_runner_delegates_assignment_lifecycle_to_generic_port() -> None:
    plan = compile_sem_paper_experiment_plan()
    events: list[str] = []

    class Isolation:
        def prepare_assignment(self, identity):
            events.append(f"prepare:{identity.assignment_id}")
            return object()

        def finalize_assignment(self, identity, receipt):
            events.append(f"finalize:{identity.assignment_id}")
            return receipt

    def factory(identity, assignment, binding):
        assert identity.assignment_id == assignment.assignment_digest
        assert binding.variant.variant_id == assignment.variant_id
        return Isolation()

    runner = SEMExperimentRunner(
        plan,
        ScriptedMinecraftEnvironment(),
        assignment_isolation_factory=factory,
    )
    assignment = plan.assignments[0]
    runner._execute_assignment(assignment, plan.binding_for(assignment.variant_id))
    assert events == [
        f"prepare:{plan.assignments[0].assignment_digest}",
        f"finalize:{plan.assignments[0].assignment_digest}",
    ]
