from __future__ import annotations

import hashlib

from noetrium.contracts import (
    ProjectModelBinding,
    ProjectModelClientPort,
    ProjectModelResponse,
    canonical_bytes,
)
from noetrium.contracts.systems.model__request import (
    ContentRef,
    ExecutionContext,
    ImmutableModelIdentity,
    ModelRequestEnvelope,
)
from projects.sem_paper.benchmarks import (
    TRACK_IDS,
    TREATMENT_IDS,
    benchmark_definition,
    build_benchmark_streams,
    build_stream,
    compare_methods,
    run_stream,
)
from projects.sem_paper.composition.model_planner import (
    ModelActionPlanner,
    PLANNER_PROMPT_DIGEST,
    PLANNER_PROMPT_GENERATION_ID,
    PLANNER_PROMPT_ID,
    PLANNER_ROLE,
    planner_model_requirement,
)
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




def test_model_planner_rejects_noncanonical_args_alias() -> None:
    try:
        ModelActionPlanner._parse_actions(
            '{"actions":[{"action_type":"goto","args":'
            '{"position":{"x":9.5,"y":72,"z":168.5},"radius":5}}]}',
            max_steps=2,
        )
    except ValueError as exc:
        assert "canonical arguments object" in str(exc)
    else:
        raise AssertionError("non-canonical args alias was accepted")

def test_model_planner_rejects_noncanonical_nested_action_shape() -> None:
    try:
        ModelActionPlanner._parse_actions(
            '{"actions":[{"action":{"tool":"move_away","distance":8}}]}',
            max_steps=4,
        )
    except ValueError as exc:
        assert "action_type must be a non-empty string" in str(exc)
    else:
        raise AssertionError("nested action shape was accepted")


def test_model_planner_accepts_json_after_non_json_prefix_and_ignores_suffix() -> None:
    plan = ModelActionPlanner._parse_actions(
        'planner-output: {"actions":[{"action_type":"wait","arguments":{}}]} trailing',
        max_steps=1,
    )
    assert plan == (("wait", {"ms": 500}, 90.0),)


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


class _RecordingModelRequests:
    def __init__(self) -> None:
        self.records = []

    @staticmethod
    def _ref(payload: bytes, media_type: str) -> ContentRef:
        return ContentRef(hashlib.sha256(payload).hexdigest(), len(payload), media_type)

    def record(self, **kwargs):
        self.records.append(dict(kwargs))
        body = canonical_bytes(kwargs["request_body"])
        compiled = kwargs.get("compiled_prompt_text")
        return ModelRequestEnvelope(
            "model-request.v1",
            kwargs["request_id"],
            kwargs["context"],
            kwargs["role"],
            kwargs["model"],
            kwargs["prompt_generation_id"],
            kwargs["prompt_id"],
            kwargs["prompt_digest"],
            self._ref(body, "application/json"),
            None if compiled is None else self._ref(compiled.encode("utf-8"), "text/plain"),
        )

    def reconstruct(self, envelope):
        raise NotImplementedError

    def reconstruct_request_body(self, envelope):
        raise NotImplementedError

    def verify_visible_request(self, envelope, actual_body):
        return None


class _TypedPlannerClient:
    def __init__(self) -> None:
        requirement = planner_model_requirement()
        self.binding = ProjectModelBinding(
            requirement_digest=requirement.digest(),
            provider_id="sem-qualified",
            provider_profile_digest="1" * 64,
            role=PLANNER_ROLE,
            model=ImmutableModelIdentity(
                "sem-qwen38-27b",
                "repo/sem-qwen38-27b",
                "rev-1",
                "vllm",
                "0.10",
                "bfloat16",
                None,
                262144,
            ),
            deployment_id="sem-qwen38-tp2",
            deployment_generation="2" * 64,
            model_stack_digest="3" * 64,
            qualification_certificate_digest="4" * 64,
            runtime_qualification_digest="5" * 64,
            host_identity_digest="6" * 64,
            prompt_generation_id=PLANNER_PROMPT_GENERATION_ID,
            prompt_id=PLANNER_PROMPT_ID,
            prompt_digest=PLANNER_PROMPT_DIGEST,
            capabilities=("generation",),
            runtime_canary_evidence_digests=("7" * 64,),
        )
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        return ProjectModelResponse(
            request.request_digest,
            self.binding.digest(),
            "8" * 64,
            '{"actions":[{"action_type":"wait","arguments":{}}]}',
            finish_reason="stop",
            input_tokens=17,
            output_tokens=5,
        )


def test_model_planner_uses_typed_client_and_stable_prompt_identity() -> None:
    client = _TypedPlannerClient()
    recorder = _RecordingModelRequests()
    assert isinstance(client, ProjectModelClientPort)
    planner = ModelActionPlanner(client, recorder)
    first_context = ExecutionContext("run-1", "trace-1", "span-1", task_id="task-1")
    second_context = ExecutionContext("run-1", "trace-1", "span-2", task_id="task-2")

    first = planner.plan(
        task={"task_id": "task-1", "goal": "wait", "max_steps": 1},
        memory_context="memory-a",
        snapshot={"inventory": []},
        context=first_context,
    )
    second = planner.plan(
        task={"task_id": "task-2", "goal": "wait elsewhere", "max_steps": 1},
        memory_context="memory-b",
        snapshot={"inventory": ["oak_log"]},
        context=second_context,
    )

    assert first == second == (("wait", {"ms": 500}, 90.0),)
    assert len(client.requests) == 2
    assert [row["prompt_digest"] for row in recorder.records] == [
        PLANNER_PROMPT_DIGEST, PLANNER_PROMPT_DIGEST
    ]
    assert recorder.records[0]["compiled_prompt_text"] != recorder.records[1]["compiled_prompt_text"]
    assert all(row["request_body"]["model"] == "sem-qwen38-27b" for row in recorder.records)
    assert all(request.requirement_digest == client.binding.requirement_digest for request in client.requests)
    assert planner.prompt_tokens == 34
    assert planner.completion_tokens == 10
