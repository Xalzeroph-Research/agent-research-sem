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
from projects.sem_paper.composition.model_planner import ModelActionPlanner
from projects.sem_paper.experiments import (
    build_benchmark,
    build_sem_paper_confirmatory_protocol,
    compile_sem_paper_experiment_plan,
)
def test_definition_is_versioned_and_deterministic() -> None:
    definition = benchmark_definition()
    assert definition.benchmark_id == "sem-evo-bench"
    assert definition.revision_id == "v2"
    assert definition.tracks == TRACK_IDS
    assert definition.digest == benchmark_definition().digest


def test_streams_are_distinct_and_complete() -> None:
    streams = build_benchmark_streams(streams_per_track=2)
    assert len(streams) == 8
    assert len({stream.digest for stream in streams}) == 8
    assert all(len(stream.episodes) == 6 for stream in streams)
    assert {stream.track_id for stream in streams} == set(TRACK_IDS)
def test_treatments_have_expected_memory_behavior() -> None:
    stream = build_stream("experience_transfer")
    no_memory = run_stream(stream, treatment_id="no_memory")
    fixed_typed = run_stream(stream, treatment_id="fixed_typed")
    sem = run_stream(stream, treatment_id="sem")

    assert no_memory.memory_cost == 0.0
    assert no_memory.generation_count == 0
    assert fixed_typed.candidate_count == 0
    assert fixed_typed.generation_count == 0
    assert sem.candidate_count == 1
    assert sem.adopted_count == 1
    assert sem.generation_count == 1
    assert sem.traces[2].generation_after == "g1"
def test_compare_methods_reports_paired_deltas() -> None:
    scores = compare_methods(
        build_benchmark_streams(
            tracks=("experience_transfer",), streams_per_track=2
        ),
    )
    assert len(scores) == 2 * len(TREATMENT_IDS)
    for score in scores:
        if score.treatment_id == "fixed_typed":
            assert score.experience_gain_auc == 0.0
            assert score.final_transfer_gain == 0.0
        if score.treatment_id == "no_memory":
            assert score.experience_gain_auc < 0.0
        assert score.as_dict()["stream_id"] == score.stream_id


def test_protocol_uses_the_12_task_primary_benchmark() -> None:
    benchmark = build_benchmark()
    protocol = build_sem_paper_confirmatory_protocol(repetitions=1)
    plan = compile_sem_paper_experiment_plan(protocol)
    assert len(benchmark.tasks) == 12
    assert tuple(variant.variant_id for variant in protocol.variants) == TREATMENT_IDS
    assert len(plan.assignments) == len(TREATMENT_IDS)
    assert protocol.metric_names
def test_model_planner_parser_is_bounded_and_hides_fixture_plan() -> None:
    task = {
        "task_id": "t1",
        "goal": "collect oak logs",
        "action_plan": [{"action_type": "wait", "arguments": {}}],
    }
    prompt = ModelActionPlanner._prompt(task, "old evidence", {"inventory": []})
    assert "action_plan" not in prompt
    plan = ModelActionPlanner._parse_actions(
        '{"actions":[{"action_type":"wait","arguments":{},"timeout_s":5}]}',
        max_steps=2,
    )
    assert plan[0][0] == "wait"
    assert plan[0][2] == 5.0




def test_model_planner_recovers_first_complete_json_object_with_trailing_brace() -> None:
    plan = ModelActionPlanner._parse_actions(
        '{"actions":[{"action":{"count":16,"tool":"move_away"}},'
        '{"action":{"count":5,"tool":"move_away"}},'
        '{"action":{"tool":"goto","position":{"x":6.5,"y":66,"z":13.3}}}]}}',
        max_steps=4,
    )
    assert [row[0] for row in plan] == ["move_away", "move_away", "goto"]
    assert plan[0][1] == {"count": 16}
    assert plan[2][1]["position"] == {"x": 6.5, "y": 66, "z": 13.3}


def test_model_planner_accepts_json_after_non_json_prefix_and_ignores_suffix() -> None:
    plan = ModelActionPlanner._parse_actions(
        'planner-output: {"actions":[{"action_type":"wait","arguments":{}}]} trailing',
        max_steps=1,
    )
    assert plan == (("wait", {}, 90.0),)


def test_model_planner_rejects_unsupported_actions() -> None:
    try:
        ModelActionPlanner._parse_actions(
            '{"actions":[{"action_type":"teleport","arguments":{}}]}',
            max_steps=2,
        )
    except ValueError as exc:
        assert "unsupported action" in str(exc)
    else:
        raise AssertionError("unsupported action was accepted")
