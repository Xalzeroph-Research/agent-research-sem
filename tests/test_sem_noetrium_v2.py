from __future__ import annotations

import pytest

from noetrium.contracts import MethodTaskOutcome, RecallRequest

from projects.sem_paper.method.self_evolving_memory import (
    SEMMethodSession,
    SEM_TREATMENTS,
    SemMethodAgentMemoryAdapter,
)


def _failure(task_id: str, failure: str) -> MethodTaskOutcome:
    return MethodTaskOutcome(
        task_id=task_id,
        family="resource",
        lineage_id=task_id,
        success=False,
        utility=-1.0,
        steps=3,
        failure_reason=failure,
        memory_queries=1,
    )


def test_treatment_surface_is_final() -> None:
    assert SEM_TREATMENTS == frozenset(
        {"no_memory", "flat_episodic", "fixed_typed", "sem"}
    )
    with pytest.raises(ValueError):
        SEMMethodSession(
            session_id="legacy",
            treatment_id="self_evolving",
            seed="run",
        )


def test_fixed_typed_initial_architecture_is_stable() -> None:
    session = SEMMethodSession(
        session_id="fixed",
        treatment_id="fixed_typed",
        seed="run",
    )
    diagnostics = session.diagnostics()
    assert diagnostics["node_count"] == 3
    assert diagnostics["edge_count"] == 2
    assert diagnostics["adopted_count"] == 0


def test_sem_creates_semantic_slot_and_backfills_evidence() -> None:
    session = SEMMethodSession(
        session_id="create",
        treatment_id="sem",
        seed="run",
    )
    session.ingest(
        {
            "task_id": "prior",
            "family": "resource",
            "state": {"inventory": ["oak_log"]},
        },
        None,
    )
    session.task_completed(_failure("failed", "precondition_missing"), {"task_id": "failed"})
    diagnostics = session.diagnostics()
    assert diagnostics["structural_mismatch_count"] == 1
    assert diagnostics["candidate_count"] == 1
    assert diagnostics["adopted_count"] == 1
    assert diagnostics["historical_backfill_count"] >= 1
    assert len(session.recall(RecallRequest("precondition_missing", None)).artifacts) >= 1


def test_sem_supports_split_merge_and_retire() -> None:
    session = SEMMethodSession(session_id="topology", treatment_id="sem", seed="run")
    session.task_completed(_failure("create", "first"), {"task_id": "create"})
    source = next(
        node.node_id
        for node in session._graph.snapshot().nodes
        if node.node_id.startswith("semantic:")
    )
    session.ingest(
        {
            "family": "resource",
            "success": False,
            "failure_reason": "split",
            "semantic_demand": {"operation": "split", "target_ids": [source]},
        },
        None,
    )
    session.task_completed(_failure("split", "split"), {"task_id": "split"})
    children = [
        node.node_id
        for node in session._graph.snapshot().nodes
        if node.node_id.startswith(source + ":")
    ]
    assert len(children) == 2
    session.ingest(
        {
            "family": "resource",
            "success": False,
            "failure_reason": "merge",
            "semantic_demand": {"operation": "merge", "target_ids": children},
        },
        None,
    )
    session.task_completed(_failure("merge", "merge"), {"task_id": "merge"})
    assert session.diagnostics()["adopted_count"] == 3
    session.ingest(
        {
            "family": "resource",
            "success": False,
            "failure_reason": "retire",
            "semantic_demand": {
                "operation": "retire",
                "target_ids": ["semantic:resource:merged"],
            },
        },
        None,
    )
    session.task_completed(_failure("retire", "retire"), {"task_id": "retire"})
    assert session.diagnostics()["adopted_count"] == 4
    assert session.diagnostics()["rejected_count"] == 0


def test_checkpoint_restore_preserves_semantic_state() -> None:
    session = SEMMethodSession(session_id="restore", treatment_id="sem", seed="run")
    session.task_completed(_failure("failed", "timeout"), {"task_id": "failed"})
    snapshot = session.checkpoint()
    restored = SEMMethodSession(session_id="restore", treatment_id="sem", seed="run")
    restored.restore(snapshot)
    assert restored.diagnostics()["graph_digest"] == session.diagnostics()["graph_digest"]
    assert restored.diagnostics()["evidence_count"] == session.diagnostics()["evidence_count"]
    assert restored.generation == session.generation


def test_no_memory_has_no_recall_surface() -> None:
    session = SEMMethodSession(session_id="none", treatment_id="no_memory", seed="run")
    session.ingest({"fact": "hidden"}, None)
    result = session.recall(RecallRequest("hidden", None))
    assert result.context_text == ""
    assert result.artifacts == ()


def test_method_does_not_own_minecraft_action_plans() -> None:
    from projects.sem_paper.composition.environment import load_scripted_action_plan

    session = SEMMethodSession(session_id="plan", treatment_id="sem", seed="run")
    assert not hasattr(session, "plan_actions")
    assert load_scripted_action_plan({"family": "combat_survival"}) == ()
    assert load_scripted_action_plan(
        {
            "action_plan": [
                {
                    "action_type": "observe",
                    "arguments": {"radius": 8},
                    "timeout_s": 10,
                }
            ]
        }
    )[0][0] == "observe"


def test_agent_adapter_keeps_session_boundary() -> None:
    session = SEMMethodSession(session_id="adapter", treatment_id="sem", seed="run")
    adapter = SemMethodAgentMemoryAdapter(session)
    assert adapter.session is session
    assert adapter.diagnostics()["treatment_id"] == "sem"


def test_fixed_typed_persists_without_architecture_evolution() -> None:
    session = SEMMethodSession(
        session_id="fixed-persistent",
        treatment_id="fixed_typed",
        seed="run",
    )
    session.ingest(
        {"task_id": "prior", "family": "resource", "state": {"inventory": ["oak_log"]}},
        None,
    )
    session.task_completed(_failure("failed", "precondition_missing"), {"task_id": "failed"})
    diagnostics = session.diagnostics()
    assert diagnostics["evidence_count"] >= 2
    assert diagnostics["memory_entry_count"] >= 2
    assert diagnostics["adopted_count"] == 0
    assert session.recall(RecallRequest("oak_log", None)).artifacts


def test_sem_runtime_adoption_is_proposal_blind() -> None:
    session = SEMMethodSession(session_id="gate", treatment_id="sem", seed="run")
    session.task_completed(_failure("failed", "precondition_missing"), {"task_id": "failed"})
    diagnostics = session.diagnostics()
    assert diagnostics["proposal_blind_gate"] is True
    assert diagnostics["online_utility_gate"] is False
    assert diagnostics["adopted_count"] == 1


def test_sem_uses_public_noetrium_memory_graph_facade() -> None:
    from noetrium.contracts.systems.components import VersionedMemoryGraph

    session = SEMMethodSession(session_id="public-contract", treatment_id="sem", seed="run")
    assert isinstance(session._graph, VersionedMemoryGraph)


def test_memory_and_audit_evidence_are_disjoint() -> None:
    session = SEMMethodSession(session_id="channels", treatment_id="sem", seed="run")
    session.ingest({"task_id": "memory", "fact": "visible"}, None)
    audit_id = session.record_audit(
        {"task_id": "audit", "success": True, "heldout": "never-memory"}
    )
    assert audit_id not in {item.evidence_id for item in session._evidence}
    assert session.diagnostics()["audit_evidence_count"] == 1
    assert "never-memory" not in session.recall(
        RecallRequest("heldout", None)
    ).context_text


def test_monitor_state_is_checkpointed() -> None:
    session = SEMMethodSession(session_id="monitor", treatment_id="sem", seed="run")
    session.task_completed(_failure("failed", "precondition_missing"), None)
    snapshot = session.checkpoint()
    restored = SEMMethodSession(session_id="monitor", treatment_id="sem", seed="run")
    restored.restore(snapshot)
    assert restored.diagnostics()["opportunity_count"] == 1
    assert (
        restored.diagnostics()["monitor_query_count"]
        == session.diagnostics()["monitor_query_count"]
    )
