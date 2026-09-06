from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable, Mapping

from noetrium.contracts import MethodTaskOutcome, RecallRequest, canonical_digest

from projects.sem_paper.method.self_evolving_memory import SEMMethodSession

TRACK_IDS = (
    "memory_core",
    "experience_transfer",
    "agentic_closed_loop",
    "environment_drift",
)
TREATMENT_IDS = ("fixed_memory", "rule_based", "self_evolving")


@dataclass(frozen=True, slots=True)
class EpisodeSpec:
    stream_id: str
    episode_id: str
    ordinal: int
    track_id: str
    family: str
    query: str
    required_memory: tuple[str, ...]
    required_policy_hint: str | None
    post_episode_payload: Mapping[str, Any]
    failure_reason: str
    validation_gain: float
    forced_failure: bool = False
    expected_abstention: bool = False

    @property
    def digest(self) -> str:
        return canonical_digest({
            "stream_id": self.stream_id,
            "episode_id": self.episode_id,
            "ordinal": self.ordinal,
            "track_id": self.track_id,
            "family": self.family,
            "query": self.query,
            "required_memory": self.required_memory,
            "required_policy_hint": self.required_policy_hint,
            "post_episode_payload": self.post_episode_payload,
            "failure_reason": self.failure_reason,
            "validation_gain": self.validation_gain,
            "forced_failure": self.forced_failure,
            "expected_abstention": self.expected_abstention,
        })
@dataclass(frozen=True, slots=True)
class TaskStream:
    stream_id: str
    track_id: str
    episodes: tuple[EpisodeSpec, ...]
    seed: str

    @property
    def digest(self) -> str:
        return canonical_digest({
            "stream_id": self.stream_id,
            "track_id": self.track_id,
            "seed": self.seed,
            "episodes": tuple(item.digest for item in self.episodes),
        })


@dataclass(frozen=True, slots=True)
class StreamTrace:
    episode_id: str
    ordinal: int
    success: bool
    recalled_memory: tuple[str, ...]
    policy_hint: str | None
    generation: str
    generation_after: str
    utility: float
    verified_effect: bool
    pending_candidates_after: int
@dataclass(frozen=True, slots=True)
class BenchmarkScore:
    treatment_id: str
    track_id: str
    stream_id: str
    experience_gain_auc: float
    final_transfer_gain: float
    adaptation_recovery: float
    negative_transfer_rate: float
    memory_cost: float
    verified_effect_rate: float
    candidate_count: int
    adopted_count: int
    rejected_count: int
    generation_count: int
    traces: tuple[StreamTrace, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "treatment_id": self.treatment_id,
            "track_id": self.track_id,
            "stream_id": self.stream_id,
            "experience_gain_auc": self.experience_gain_auc,
            "final_transfer_gain": self.final_transfer_gain,
            "adaptation_recovery": self.adaptation_recovery,
            "negative_transfer_rate": self.negative_transfer_rate,
            "memory_cost": self.memory_cost,
            "verified_effect_rate": self.verified_effect_rate,
            "candidate_count": self.candidate_count,
            "adopted_count": self.adopted_count,
            "rejected_count": self.rejected_count,
            "generation_count": self.generation_count,
        }


@dataclass(frozen=True, slots=True)
class SEMEvoBenchDefinition:
    benchmark_id: str
    revision_id: str
    tracks: tuple[str, ...]
    protocol_version: str
    scoring_version: str
    fixture_digest: str

    @property
    def digest(self) -> str:
        return canonical_digest({
            "benchmark_id": self.benchmark_id,
            "revision_id": self.revision_id,
            "tracks": self.tracks,
            "protocol_version": self.protocol_version,
            "scoring_version": self.scoring_version,
            "fixture_digest": self.fixture_digest,
        })
def _episode(
    stream_id: str,
    track_id: str,
    ordinal: int,
    family: str,
    query: str,
    *,
    required_memory: tuple[str, ...] = (),
    required_policy_hint: str | None = None,
    payload: Mapping[str, Any] | None = None,
    failure_reason: str = "",
    validation_gain: float = 0.0,
    forced_failure: bool = False,
    expected_abstention: bool = False,
) -> EpisodeSpec:
    return EpisodeSpec(
        stream_id=stream_id,
        episode_id=f"{stream_id}:e{ordinal}",
        ordinal=ordinal,
        track_id=track_id,
        family=family,
        query=query,
        required_memory=required_memory,
        required_policy_hint=required_policy_hint,
        post_episode_payload=dict(payload or {}),
        failure_reason=failure_reason,
        validation_gain=validation_gain,
        forced_failure=forced_failure,
        expected_abstention=expected_abstention,
    )


def build_stream(track_id: str, stream_index: int = 0) -> TaskStream:
    if track_id not in TRACK_IDS:
        raise ValueError(f"unknown SEM-EvoBench track: {track_id}")
    stream_id = f"{track_id}:stream-{stream_index:03d}"
    if track_id == "memory_core":
        episodes = (
            _episode(stream_id, track_id, 0, "fact_acquisition",
                     "learn fact_v1", payload={"memory_key": "fact_v1"}),
            _episode(stream_id, track_id, 1, "fact_recall",
                     "recall fact_v1", required_memory=("fact_v1",)),
            _episode(stream_id, track_id, 2, "knowledge_update",
                     "learn fact_v2", payload={"memory_key": "fact_v2"}),
            _episode(stream_id, track_id, 3, "updated_recall",
                     "recall fact_v2", required_memory=("fact_v2",)),
            _episode(stream_id, track_id, 4, "abstention",
                     "abstain on unknown fact", required_memory=("never_seen",),
                     expected_abstention=True),
            _episode(stream_id, track_id, 5, "heldout_recall",
                     "recall fact_v2", required_memory=("fact_v2",)),
        )
    elif track_id == "experience_transfer":
        episodes = (
            _episode(stream_id, track_id, 0, "procedure_learning",
                     "learn procedure_v1", payload={"memory_key": "procedure_v1"}),
            _episode(stream_id, track_id, 1, "novel_transfer",
                     "apply procedure_v1", required_memory=("procedure_v1",)),
            _episode(stream_id, track_id, 2, "failure_recovery",
                     "recover from timeout using procedure_v1",
                     required_memory=("procedure_v1",), failure_reason="timeout",
                     forced_failure=True),
            _episode(stream_id, track_id, 3, "adaptation_transfer",
                     "apply the shorter action policy",
                     required_policy_hint="candidate-timeout", validation_gain=0.5),
            _episode(stream_id, track_id, 4, "heldout_procedure",
                     "learn procedure_v2", payload={"memory_key": "procedure_v2"}),
            _episode(stream_id, track_id, 5, "final_transfer",
                     "apply procedure_v2", required_memory=("procedure_v2",)),
        )
    elif track_id == "agentic_closed_loop":
        episodes = (
            _episode(stream_id, track_id, 0, "subgoal_discovery",
                     "discover object_a", payload={"memory_key": "object_a"}),
            _episode(stream_id, track_id, 1, "dependent_action",
                     "use object_a", required_memory=("object_a",)),
            _episode(stream_id, track_id, 2, "action_feedback",
                     "recover from blocked action", required_memory=("object_a",),
                     failure_reason="blocked", forced_failure=True),
            _episode(stream_id, track_id, 3, "next_action",
                     "retry from grounded state", required_policy_hint="candidate-blocked",
                     validation_gain=0.5),
            _episode(stream_id, track_id, 4, "new_subgoal",
                     "discover object_b", payload={"memory_key": "object_b"}),
            _episode(stream_id, track_id, 5, "heldout_dependency",
                     "use object_b", required_memory=("object_b",)),
        )
    else:
        episodes = (
            _episode(stream_id, track_id, 0, "world_rule_v1",
                     "learn world_rule_v1", payload={"memory_key": "world_rule_v1"}),
            _episode(stream_id, track_id, 1, "stable_world",
                     "apply world_rule_v1", required_memory=("world_rule_v1",)),
            _episode(stream_id, track_id, 2, "environment_drift",
                     "recover from blocked interaction",
                     required_memory=("world_rule_v1",), failure_reason="blocked",
                     forced_failure=True),
            _episode(stream_id, track_id, 3, "drift_adaptation",
                     "apply grounded recovery policy",
                     required_policy_hint="candidate-blocked", validation_gain=0.5),
            _episode(stream_id, track_id, 4, "new_world_rule",
                     "learn world_rule_v2", payload={"memory_key": "world_rule_v2"}),
            _episode(stream_id, track_id, 5, "post_drift_transfer",
                     "apply world_rule_v2", required_memory=("world_rule_v2",)),
        )
    return TaskStream(stream_id, track_id, episodes, f"seed-{stream_index:03d}")
def build_benchmark_streams(
    *,
    tracks: Iterable[str] = TRACK_IDS,
    streams_per_track: int = 2,
) -> tuple[TaskStream, ...]:
    if streams_per_track < 1:
        raise ValueError("streams_per_track must be positive")
    selected = tuple(tracks)
    if not selected:
        raise ValueError("at least one SEM-EvoBench track is required")
    return tuple(
        build_stream(track_id, index)
        for track_id in selected
        for index in range(streams_per_track)
    )


def benchmark_definition() -> SEMEvoBenchDefinition:
    return SEMEvoBenchDefinition(
        benchmark_id="sem-evo-bench",
        revision_id="v1",
        tracks=TRACK_IDS,
        protocol_version="memory-agent-environment-loop.v1",
        scoring_version="paired-control-deltas.v1",
        fixture_digest=canonical_digest(
            {track_id: build_stream(track_id, 0).digest for track_id in TRACK_IDS}
        ),
    )


def _required_memory_found(
    episode: EpisodeSpec,
    recalled_memory: str,
    policy_overrides: Mapping[str, str],
) -> bool:
    memory_found = all(key in recalled_memory for key in episode.required_memory)
    if episode.expected_abstention:
        return not memory_found and episode.required_policy_hint is None
    if not memory_found:
        return False
    if episode.required_policy_hint is not None:
        return any(
            value == episode.required_policy_hint
            or value.startswith(episode.required_policy_hint + "-")
            for value in policy_overrides.values()
        )
    return True


def _candidate_feedback(session: SEMMethodSession, episode: EpisodeSpec) -> None:
    # Validation is intentionally delayed until the next episode. This makes
    # adaptation latency observable instead of granting self-evolution credit
    # on the same failed episode that proposed the candidate.
    if episode.validation_gain == 0.0:
        return
    for candidate in session.pending_candidates():
        session.validate_and_apply(
            candidate.candidate_id,
            episode.family,
            {
                "verified": episode.validation_gain > 0.0,
                "utility_delta": episode.validation_gain,
            },
        )
def run_stream(
    stream: TaskStream,
    *,
    treatment_id: str,
    session_id: str | None = None,
) -> BenchmarkScore:
    if treatment_id not in TREATMENT_IDS:
        raise ValueError(f"unknown SEM treatment: {treatment_id}")
    session = SEMMethodSession(
        session_id=session_id or stream.stream_id,
        treatment_id=treatment_id,
        seed=stream.seed,
        adaptive=treatment_id != "fixed_memory",
        initial_memory=(),
    )
    traces: list[StreamTrace] = []
    for episode in stream.episodes:
        before = session.recall(RecallRequest(episode.query, episode.digest, limit=8))
        before_diagnostics = session.diagnostics()
        policy_overrides = dict(before_diagnostics["policy_overrides"])
        action_generation = str(before_diagnostics["generation"])
        action_policy = next(
            (
                value for value in policy_overrides.values()
                if episode.required_policy_hint == value
            ),
            None,
        )
        success = _required_memory_found(
            episode, before.context_text, policy_overrides
        ) and not episode.forced_failure
        outcome = MethodTaskOutcome(
            task_id=episode.episode_id,
            family=episode.family,
            lineage_id=episode.digest,
            success=success,
            utility=1.0 if success else -0.25,
            steps=1 if success else 2,
            failure_reason="" if success else (episode.failure_reason or "blocked"),
            memory_queries=1,
        )
        session.task_completed(outcome, episode.digest)
        if episode.post_episode_payload:
            session.ingest(episode.post_episode_payload, episode.digest)
        _candidate_feedback(session, episode)
        after_diagnostics = session.diagnostics()
        traces.append(StreamTrace(
            episode_id=episode.episode_id,
            ordinal=episode.ordinal,
            success=success,
            recalled_memory=before.artifacts,
            policy_hint=action_policy,
            generation=action_generation,
            generation_after=str(after_diagnostics["generation"]),
            utility=outcome.utility,
            verified_effect=success,
            pending_candidates_after=int(after_diagnostics["pending_candidate_count"]),
        ))
    successes = [float(item.success) for item in traces]
    forced_indices = [
        index for index, episode in enumerate(stream.episodes)
        if episode.forced_failure
    ]
    if not forced_indices:
        recovery = 0.0
    else:
        first_failure = forced_indices[0]
        recovery = float(next(
            (
                index - first_failure
                for index in range(first_failure + 1, len(traces))
                if traces[index].success
            ),
            len(traces) - first_failure,
        ))
    negative = sum(
        item.success is False and item.ordinal > 0 for item in traces
    )
    diagnostics = session.diagnostics()
    return BenchmarkScore(
        treatment_id=treatment_id,
        track_id=stream.track_id,
        stream_id=stream.stream_id,
        experience_gain_auc=sum(successes) / max(1, len(successes)),
        final_transfer_gain=successes[-1] if successes else 0.0,
        adaptation_recovery=recovery,
        negative_transfer_rate=negative / max(1, len(traces) - 1),
        memory_cost=float(diagnostics["entry_count"]),
        verified_effect_rate=sum(
            float(item.verified_effect) for item in traces
        ) / max(1, len(traces)),
        candidate_count=int(diagnostics["candidate_count"]),
        adopted_count=int(diagnostics["adopted_count"]),
        rejected_count=int(diagnostics["rejected_count"]),
        generation_count=int(str(diagnostics["generation"])[1:]),
        traces=tuple(traces),
    )
def compare_methods(
    streams: Iterable[TaskStream],
    treatments: Iterable[str] = TREATMENT_IDS,
) -> tuple[BenchmarkScore, ...]:
    selected_streams = tuple(streams)
    selected_treatments = tuple(treatments)
    if not selected_streams:
        raise ValueError("at least one task stream is required")
    raw_scores = tuple(
        run_stream(
            stream,
            treatment_id=treatment_id,
            session_id=f"{treatment_id}:{stream.stream_id}",
        )
        for stream in selected_streams
        for treatment_id in selected_treatments
    )
    controls = {
        score.stream_id: score
        for score in raw_scores
        if score.treatment_id == "fixed_memory"
    }
    # Report gain metrics as paired deltas against the immutable control on the
    # exact same stream. Raw treatment trajectories remain in traces.
    return tuple(
        replace(
            score,
            experience_gain_auc=(
                score.experience_gain_auc
                - controls[score.stream_id].experience_gain_auc
                if score.stream_id in controls
                else score.experience_gain_auc
            ),
            final_transfer_gain=(
                score.final_transfer_gain
                - controls[score.stream_id].final_transfer_gain
                if score.stream_id in controls
                else score.final_transfer_gain
            ),
        )
        for score in raw_scores
    )


__all__ = [
    "TRACK_IDS",
    "TREATMENT_IDS",
    "EpisodeSpec",
    "TaskStream",
    "StreamTrace",
    "BenchmarkScore",
    "SEMEvoBenchDefinition",
    "benchmark_definition",
    "build_stream",
    "build_benchmark_streams",
    "run_stream",
    "compare_methods",
]
