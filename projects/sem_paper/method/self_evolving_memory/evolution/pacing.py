from __future__ import annotations

"""Adaptive review pacing derived only from diagnostic symptoms."""

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Sequence

from research_platform.platform.kernel import JsonObject
from ..architecture import MemoryArchitectureSpec
from .telemetry import TelemetryBook

@dataclass(frozen=True, slots=True)
class AdoptionObservation:
    architecture_generation: int
    accepted: bool


@dataclass(frozen=True, slots=True)
class AdaptiveSlowClockConfig:
    base_horizon_episodes: int = 8
    min_horizon_episodes: int = 4
    max_horizon_episodes: int = 18
    high_symptom_density: float = 0.35
    low_symptom_density: float = 0.08
    recent_edit_penalty: int = 4

    def __post_init__(self) -> None:
        if not 0 < self.min_horizon_episodes <= self.base_horizon_episodes <= self.max_horizon_episodes:
            raise ValueError("slow-clock horizon ordering is invalid")
        if not 0.0 <= self.low_symptom_density <= self.high_symptom_density:
            raise ValueError("slow-clock symptom thresholds are invalid")
        if self.recent_edit_penalty < 0:
            raise ValueError("slow-clock edit penalty must be non-negative")


@dataclass(frozen=True, slots=True)
class NodeHorizon:
    node_id: str
    symptom_density: float
    required_episodes: int


class AdaptiveSlowClock:
    """Observation pacing derived from neutral symptoms, never an edit gate."""

    def __init__(self, config: AdaptiveSlowClockConfig | None = None) -> None:
        self.config = config or AdaptiveSlowClockConfig()

    def horizons(
        self,
        *,
        architecture: MemoryArchitectureSpec,
        telemetry: TelemetryBook,
        recent_adoptions: Sequence[AdoptionObservation],
    ) -> tuple[NodeHorizon, ...]:
        config = self.config
        query_counts = Counter(node_id for query in telemetry.queries[-64:] for node_id in query.selected_nodes)
        incident_counts = Counter(node_id for incident in telemetry.incidents[-64:] for node_id in incident.node_ids)
        recent_accept = next((item for item in reversed(recent_adoptions) if item.accepted), None)
        output: list[NodeHorizon] = []
        for node in architecture.nodes:
            queries = query_counts[node.node_id]
            density = incident_counts[node.node_id] / max(1, queries)
            horizon = config.base_horizon_episodes
            if density >= config.high_symptom_density:
                horizon -= 2
            elif density <= config.low_symptom_density:
                horizon += 2
            if recent_accept is not None and architecture.generation - recent_accept.architecture_generation <= 1:
                horizon += config.recent_edit_penalty
            horizon = max(config.min_horizon_episodes, min(config.max_horizon_episodes, horizon))
            output.append(NodeHorizon(node.node_id, density, horizon))
        return tuple(sorted(output, key=lambda item: item.node_id))

    def allow_review(
        self,
        *,
        architecture: MemoryArchitectureSpec,
        telemetry: TelemetryBook,
        recent_adoptions: Sequence[AdoptionObservation],
        episodes_since_activation: int,
    ) -> tuple[bool, JsonObject]:
        if episodes_since_activation < 0:
            raise ValueError("slow-clock episode count cannot be negative")
        horizons = self.horizons(
            architecture=architecture,
            telemetry=telemetry,
            recent_adoptions=recent_adoptions,
        )
        symptomatic = tuple(item for item in horizons if item.symptom_density > 0)
        required = min(
            (item.required_episodes for item in symptomatic),
            default=self.config.base_horizon_episodes,
        )
        facts = {
            "required_episodes": required,
            "episodes_since_activation": episodes_since_activation,
            "node_horizons": [asdict(item) for item in horizons],
        }
        return episodes_since_activation >= required, facts
