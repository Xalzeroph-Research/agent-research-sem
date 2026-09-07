from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Iterable, Mapping

from noetrium.contracts import MethodTaskOutcome, RecallRequest, canonical_digest
from projects.sem_paper.method.self_evolving_memory import SEMMethodSession

TRACK_IDS = ("memory_retrieval", "experience_transfer", "closed_loop_recovery", "world_change")
TREATMENT_IDS = ("no_memory", "flat_episodic", "fixed_typed", "sem")


@dataclass(frozen=True, slots=True)
class EpisodeSpec:
    episode_id: str
    ordinal: int
    track_id: str
    family: str
    query: str
    required_memory: tuple[str, ...] = ()
    post_episode_payload: Mapping[str, Any] | None = None
    forced_failure: bool = False

    @property
    def digest(self) -> str:
        return canonical_digest(asdict(self))


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
            "episodes": [asdict(episode) for episode in self.episodes],
            "seed": self.seed,
        })


@dataclass(frozen=True, slots=True)
class StreamTrace:
    episode_id: str
    ordinal: int
    success: bool
    recalled_memory: tuple[str, ...]
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
        payload = asdict(self)
        payload["traces"] = [asdict(trace) for trace in self.traces]
        return payload


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
        return canonical_digest(asdict(self))


def _episode(stream_id: str, track_id: str, ordinal: int, family: str, query: str,
            *, required_memory: tuple[str, ...] = (), payload: Mapping[str, Any] | None = None,
            forced_failure: bool = False) -> EpisodeSpec:
    return EpisodeSpec(f"{stream_id}:episode-{ordinal:02d}", ordinal, track_id, family,
                       query, required_memory, payload, forced_failure)


def build_stream(track_id: str, stream_index: int = 0) -> TaskStream:
    if track_id not in TRACK_IDS:
        raise ValueError(f"unknown track: {track_id}")
    stream_id = f"{track_id}:stream-{stream_index:03d}"
    key_a, key_b = f"{track_id}:a", f"{track_id}:b"
    episodes = (
        _episode(stream_id, track_id, 0, "discovery", f"learn {key_a}", payload={"memory_key": key_a}),
        _episode(stream_id, track_id, 1, "reuse", f"use {key_a}", required_memory=(key_a,)),
        _episode(stream_id, track_id, 2, "recovery", f"recover {key_a}", required_memory=(key_a,), forced_failure=True),
        _episode(stream_id, track_id, 3, "adaptation", f"replan after recovery"),
        _episode(stream_id, track_id, 4, "discovery", f"learn {key_b}", payload={"memory_key": key_b}),
        _episode(stream_id, track_id, 5, "heldout_transfer", f"use {key_b}", required_memory=(key_b,)),
    )
    return TaskStream(stream_id, track_id, episodes, f"seed-{stream_index:03d}")


def build_benchmark_streams(*, tracks: Iterable[str] = TRACK_IDS, streams_per_track: int = 2) -> tuple[TaskStream, ...]:
    if streams_per_track < 1:
        raise ValueError("streams_per_track must be positive")
    selected = tuple(tracks)
    if not selected:
        raise ValueError("at least one track is required")
    return tuple(build_stream(track, index) for track in selected for index in range(streams_per_track))


def benchmark_definition() -> SEMEvoBenchDefinition:
    return SEMEvoBenchDefinition(
        "sem-evo-bench", "v2", TRACK_IDS, "memory-agent-environment-loop.v2",
        "paired-stream-deltas.v2",
        canonical_digest({track: build_stream(track).digest for track in TRACK_IDS}),
    )


def run_stream(stream: TaskStream, *, treatment_id: str, session_id: str | None = None) -> BenchmarkScore:
    if treatment_id not in TREATMENT_IDS:
        raise ValueError(f"unknown treatment: {treatment_id}")
    session = SEMMethodSession(
        session_id=session_id or stream.stream_id,
        treatment_id=treatment_id,
        seed=stream.seed,
        adaptive=treatment_id == "sem",
    )
    traces: list[StreamTrace] = []
    for episode in stream.episodes:
        generation_before = session.generation
        before = session.recall(RecallRequest(episode.query, None, limit=8))
        success = (
            all(key in before.context_text for key in episode.required_memory)
            and not episode.forced_failure
        )
        outcome = MethodTaskOutcome(
            task_id=episode.episode_id, family=episode.family, lineage_id=episode.digest,
            success=success, utility=1.0 if success else -0.25,
            steps=1 if success else 2,
            failure_reason="" if success else "blocked",
            memory_queries=1,
        )
        session.task_completed(outcome, episode.digest)
        if episode.post_episode_payload:
            session.ingest(episode.post_episode_payload, episode.digest)
        diagnostics = session.diagnostics()
        traces.append(StreamTrace(
            episode.episode_id, episode.ordinal, success, before.artifacts,
            generation_before, str(diagnostics["generation"]),
            outcome.utility, success, int(diagnostics["candidate_count"]),
        ))
    successes = [float(trace.success) for trace in traces]
    diagnostics = session.diagnostics()
    recovery = next(
        (trace.ordinal - 2 for trace in traces if trace.ordinal > 2 and trace.success), 0.0
    )
    return BenchmarkScore(
        treatment_id, stream.track_id, stream.stream_id,
        sum(successes) / max(1, len(successes)),
        successes[-1] if successes else 0.0,
        recovery,
        sum(not trace.success for trace in traces[1:]) / max(1, len(traces) - 1),
        float(diagnostics["memory_entry_count"]),
        sum(float(trace.verified_effect) for trace in traces) / max(1, len(traces)),
        int(diagnostics["candidate_count"]), int(diagnostics["adopted_count"]),
        int(diagnostics["rejected_count"]),
        int(str(diagnostics["generation"])[1:]),
        tuple(traces),
    )


def compare_methods(streams: Iterable[TaskStream], treatments: Iterable[str] = TREATMENT_IDS) -> tuple[BenchmarkScore, ...]:
    selected_streams, selected_treatments = tuple(streams), tuple(treatments)
    if not selected_streams:
        raise ValueError("at least one task stream is required")
    raw = tuple(run_stream(stream, treatment_id=treatment)
                for stream in selected_streams for treatment in selected_treatments)
    controls = {score.stream_id: score for score in raw if score.treatment_id == "fixed_typed"}
    if any(score.treatment_id != "fixed_typed" and score.stream_id not in controls for score in raw):
        raise ValueError("compare_methods requires fixed_typed as the paired reference")
    return tuple(
        replace(
            score,
            experience_gain_auc=score.experience_gain_auc - controls[score.stream_id].experience_gain_auc
                if score.stream_id in controls and score.treatment_id != "fixed_typed"
                else 0.0 if score.treatment_id == "fixed_typed" else score.experience_gain_auc,
            final_transfer_gain=score.final_transfer_gain - controls[score.stream_id].final_transfer_gain
                if score.stream_id in controls and score.treatment_id != "fixed_typed"
                else 0.0 if score.treatment_id == "fixed_typed" else score.final_transfer_gain,
        )
        for score in raw
    )


__all__ = [
    "TRACK_IDS", "TREATMENT_IDS", "EpisodeSpec", "TaskStream", "StreamTrace",
    "BenchmarkScore", "SEMEvoBenchDefinition", "benchmark_definition",
    "build_stream", "build_benchmark_streams", "run_stream", "compare_methods",
]
