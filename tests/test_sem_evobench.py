from __future__ import annotations

from projects.sem_paper.benchmarks import (
    TRACK_IDS,
    TREATMENT_IDS,
    benchmark_definition,
    build_benchmark_streams,
    build_stream,
    compare_methods,
    run_stream,
)
from projects.sem_paper.method.self_evolving_memory import SEMMethodSession


def test_definition_binds_reference_fixtures() -> None:
    definition = benchmark_definition()
    assert definition.benchmark_id == "sem-evo-bench"
    assert definition.tracks == TRACK_IDS
    assert definition.digest


def test_streams_are_distinct_and_complete() -> None:
    streams = build_benchmark_streams(streams_per_track=2)
    assert len(streams) == 8
    assert len({stream.digest for stream in streams}) == 8
    assert all(len(stream.episodes) == 6 for stream in streams)
    assert {stream.track_id for stream in streams} == set(TRACK_IDS)


def test_fixed_memory_is_immutable() -> None:
    score = run_stream(build_stream("memory_core"), treatment_id="fixed_memory")
    assert score.candidate_count == 0
    assert score.generation_count == 0
    assert score.memory_cost == 0.0


def test_rule_and_self_have_observable_validation_latency() -> None:
    stream = build_stream("experience_transfer")
    rule = run_stream(stream, treatment_id="rule_based")
    self_evolving = run_stream(stream, treatment_id="self_evolving")
    assert rule.adopted_count == 1
    assert self_evolving.adopted_count == 1
    assert self_evolving.rejected_count == 0
    assert rule.adaptation_recovery == 1.0
    assert self_evolving.adaptation_recovery == 2.0
    assert rule.traces[3].success is True
    assert self_evolving.traces[3].success is False
    assert self_evolving.traces[3].generation_after == "g1"


def test_self_rejects_unverified_candidate() -> None:
    session = SEMMethodSession(
        session_id="reject", treatment_id="self_evolving",
        seed="Seed-C", adaptive=True,
    )
    session.task_completed({
        "task_id": "t1", "family": "transfer", "lineage_id": "t1",
        "success": False, "utility": -1, "steps": 2,
        "failure_reason": "timeout",
    }, None)
    candidate = session.pending_candidates()[0]
    assert session.validate_and_apply(
        candidate.candidate_id, "transfer",
        {"verified": False, "utility_delta": -0.1},
    ) is False
    assert session.generation == "g0"
    assert session.diagnostics()["rejected_count"] == 1


def test_compare_methods_reports_paired_gains() -> None:
    scores = compare_methods(
        build_benchmark_streams(tracks=("experience_transfer",), streams_per_track=2),
    )
    assert len(scores) == 2 * len(TREATMENT_IDS)
    controls = [score for score in scores if score.treatment_id == "fixed_memory"]
    treatments = [score for score in scores if score.treatment_id != "fixed_memory"]
    assert all(score.experience_gain_auc == 0.0 for score in controls)
    assert all(score.experience_gain_auc > 0.0 for score in treatments)



def test_external_preparation_keeps_execution_outside_adapter(tmp_path) -> None:
    source = tmp_path / "memory_tasks.json"
    source.write_text(
        '{"tasks":[{"task_id":"m1","goal":"remember x","family":"memory"}]}',
        encoding="utf-8",
    )
    from projects.sem_paper.benchmarks import prepare_external_benchmark

    prepared = prepare_external_benchmark("memory-agent-bench", source)
    payload = prepared.as_dict()
    assert payload["execution_owner"] == "sem+noetrium"
    assert payload["task_count"] == 1
    assert payload["claim_status"] == "metadata_prepared"
