from __future__ import annotations

import json

import pytest

from projects.sem_paper.experiments.analysis import (
    analyze_run,
    bootstrap_mean_ci,
    load_assignment_records,
    paired_permutation_ci,
)
from projects.sem_paper.method.self_evolving_memory import (
    EvidenceEvent,
    NeutralArchitectureObservation,
    SEMMethodSession,
    TransformSpec,
    validate_transform,
)
from noetrium.contracts import MethodTaskOutcome


def test_canonical_evidence_event_has_all_design_fields() -> None:
    event = EvidenceEvent.build(
        task_id="task-1",
        family="resource_collection",
        payload={
            "episode_id": "episode-1",
            "world_id": "world-1",
            "observation_id": "obs-1",
            "action_id": "action-1",
            "effect_receipt": {"verified": True},
            "success": False,
            "failure_reason": "missing_tool",
            "timestamp_ms": 123,
            "entity_refs": ["player"],
            "position_refs": ["0,64,0"],
            "source_refs": ["minecraft"],
        },
        source="environment",
        generation="g0",
    )
    assert event.episode_id == "episode-1"
    assert event.world_state_ref == "world-1"
    assert event.observation_ref == "obs-1"
    assert event.action_ref == "action-1"
    assert event.effect_receipt["verified"] is True
    assert event.outcome["success"] is False
    assert event.entity_refs == ("player",)
    assert event.position_refs == ("0,64,0",)
    assert event.source_refs == ("minecraft",)
    assert event.provenance["source"] == "environment"


def test_transform_ir_is_restricted_and_json_only() -> None:
    spec = TransformSpec("SEMANTIC_REDUCE", arguments={"selector": "failure"})
    assert spec.canonical_kind == "SEMANTIC_REDUCE"
    assert validate_transform(spec.as_mapping())[0]
    assert not validate_transform({
        "kind": "SEMANTIC_MAP",
        "code": "lambda x: x",
    })[0]
    with pytest.raises(ValueError):
        TransformSpec("UNKNOWN")


def test_neutral_observation_does_not_emit_architecture_advice() -> None:
    observation = NeutralArchitectureObservation(
        {"fields": ["task_id"]},
        {"queries": 2},
        {"hits": 1},
        ({"incident": "unresolved"},),
        {"cluster:1": 2},
        {},
        {"active_nodes": 3},
        {"events": 1},
    )
    data = observation.as_dict()
    assert "recommended_edit" not in data
    assert "target_node" not in data
    assert observation.digest()


def test_checkpoint_restores_proposal_and_ledger() -> None:
    session = SEMMethodSession(
        session_id="design-surface",
        treatment_id="sem",
        seed="seed",
    )
    session.task_completed(
        MethodTaskOutcome(
            task_id="failed",
            family="resource",
            lineage_id="failed",
            success=False,
            utility=-1.0,
            steps=2,
            failure_reason="missing_tool",
            memory_queries=1,
        ),
        None,
    )
    snapshot = session.checkpoint()
    assert session.diagnostics()["evolution_ledger_count"] >= 3
    restored = SEMMethodSession(
        session_id="design-surface",
        treatment_id="sem",
        seed="seed",
    )
    restored.restore(snapshot)
    assert (
        restored.diagnostics()["evolution_ledger_digest"]
        == session.diagnostics()["evolution_ledger_digest"]
    )
    assert restored.checkpoint().payload_sha256 == snapshot.payload_sha256


def test_analysis_uses_assignment_as_statistical_unit(tmp_path) -> None:
    for treatment, success in (("fixed_typed", True), ("sem", False)):
        path = tmp_path / f"{treatment}.json"
        path.write_text(json.dumps({
            "assignment": {
                "assignment_id": treatment,
                "variant_id": treatment,
                "repetition": 0,
            },
            "diagnostics": {
                "candidate_count": 1 if treatment == "sem" else 0,
                "adopted_count": 1 if treatment == "sem" else 0,
                "evidence_count": 2,
                "historical_backfill_count": 1 if treatment == "sem" else 0,
            },
            "tasks": [
                {
                    "task_id": "task",
                    "family": "long_horizon_mixed",
                    "success": success,
                    "utility": 1 if success else -1,
                    "steps": 4,
                    "duration_s": 2,
                    "memory_queries": 1,
                }
            ],
        }), encoding="utf-8")
    records = load_assignment_records(tmp_path)
    result = analyze_run(records)
    assert result["assignment_count"] == 2
    assert result["statistical_unit"] == "assignment"
    assert result["paired_sem_minus_fixed_typed"]["success_rate"]["deltas"] == [-1.0]
    assert bootstrap_mean_ci([1, 1, 1])[0] == 1.0
    assert paired_permutation_ci([0.5])[0] == 0.5
