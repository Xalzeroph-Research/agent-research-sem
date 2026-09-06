from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
import math
from types import MappingProxyType
from typing import Protocol, TypeAlias
from ..architecture import ArchitectureEdit, MemoryArchitectureSpec

from research_platform.experimentation.evaluation.api import ComparabilityProof
from research_platform.platform.kernel import ExecutionContext, JsonInput


StructuralIntentPayloadValue: TypeAlias = JsonInput | MemoryArchitectureSpec | ArchitectureEdit
StructuralIntentPayload: TypeAlias = Mapping[str, StructuralIntentPayloadValue]


class EditKind(StrEnum):
    NO_EDIT = "NO_EDIT"
    CREATE = "CREATE"
    RETIRE = "RETIRE"
    SPLIT = "SPLIT"
    MERGE = "MERGE"


class PrimitiveEditKind(StrEnum):
    CREATE = "CREATE"
    RETIRE = "RETIRE"


class EvolutionStage(StrEnum):
    ELIGIBILITY = "eligibility"
    DIAGNOSIS = "diagnosis"
    SYNTHESIS = "synthesis"
    COMPILATION = "compilation"
    EVALUATION = "evaluation"
    ACCEPTANCE = "acceptance"
    ADOPTION = "adoption"


class EvolutionStageFailure(RuntimeError):
    """Stable stage attribution while preserving the original exception as the cause."""

    def __init__(self, stage: EvolutionStage, cause: BaseException) -> None:
        super().__init__(f"SEM evolution stage failed: {stage.value}")
        self.stage = stage
        self.cause = cause
        self.cause_type = type(cause).__name__

    @property
    def failure_correlation_refs(self) -> tuple[str, ...]:
        return (f"evolution-stage:{self.stage.value}",)


@dataclass(frozen=True, slots=True)
class EvolutionEligibility:
    eligible: bool
    reason_code: str

    def __post_init__(self) -> None:
        if not isinstance(self.eligible, bool):
            raise ValueError("evolution eligibility flag must be boolean")
        if not isinstance(self.reason_code, str) or not self.reason_code.strip():
            raise ValueError("evolution eligibility reason_code must be a non-empty string")


@dataclass(frozen=True, slots=True)
class NodeObservationProfile:
    """Typed, neutral runtime facts shared by every evolution proposal policy."""

    node_id: str
    selected_count: int = 0
    result_count: int = 0
    query_count: int = 0
    empty_result_count: int = 0
    update_count: int = 0
    records_added: int = 0
    records_removed: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str) or not self.node_id.strip():
            raise ValueError("node observation profile requires a non-empty string node id")
        values = (
            self.selected_count,
            self.result_count,
            self.query_count,
            self.empty_result_count,
            self.update_count,
            self.records_added,
            self.records_removed,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
            raise ValueError("node observation counts must be non-negative integers")


@dataclass(frozen=True, slots=True)
class NodePairObservation:
    """Neutral co-selection fact; it carries no edit recommendation."""

    pair_id: str
    left_node_id: str
    right_node_id: str
    co_select_count: int

    def __post_init__(self) -> None:
        identities = (self.pair_id, self.left_node_id, self.right_node_id)
        if any(not isinstance(value, str) or not value.strip() for value in identities):
            raise ValueError("node pair observation identity is required")
        if self.left_node_id == self.right_node_id:
            raise ValueError("node pair observation must reference distinct nodes")
        if isinstance(self.co_select_count, bool) or not isinstance(self.co_select_count, int) or self.co_select_count < 0:
            raise ValueError("node pair co_select_count must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class UnresolvedIntentCluster:
    """Ontology-free unresolved-intent support exposed to proposal policies."""

    cluster_id: str
    support: int
    examples: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.cluster_id, str) or not self.cluster_id.strip():
            raise ValueError("unresolved intent cluster identity is required")
        if isinstance(self.support, bool) or not isinstance(self.support, int) or self.support <= 0:
            raise ValueError("unresolved intent cluster support must be a positive integer")
        if not isinstance(self.examples, tuple) or any(
            not isinstance(example, str) or not example.strip() for example in self.examples
        ):
            raise ValueError("unresolved intent cluster examples must be non-empty strings")
        if len(self.examples) > self.support:
            raise ValueError("unresolved intent cluster examples cannot exceed support")


@dataclass(frozen=True, slots=True)
class ArchitectureObservationReport:
    generation: str
    neutral_summary: str
    evidence_refs: tuple[str, ...]
    architecture: MemoryArchitectureSpec | None = None
    node_profiles: tuple[NodeObservationProfile, ...] = ()
    pairs: tuple[NodePairObservation, ...] = ()
    incident_counts: tuple[tuple[str, int], ...] = ()
    unresolved_intent_clusters: tuple[UnresolvedIntentCluster, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.generation, str) or not self.generation.strip():
            raise ValueError("architecture observation generation is required")
        if not isinstance(self.neutral_summary, str) or not self.neutral_summary.strip():
            raise ValueError("architecture observation neutral summary is required")
        if not isinstance(self.evidence_refs, tuple) or any(
            not isinstance(ref, str) or not ref.strip() for ref in self.evidence_refs
        ):
            raise ValueError("architecture observation evidence refs must be non-empty strings")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("architecture observation contains duplicate evidence refs")
        if self.architecture is not None and not isinstance(self.architecture, MemoryArchitectureSpec):
            raise ValueError("architecture observation architecture must be typed")
        if not isinstance(self.node_profiles, tuple) or any(
            not isinstance(profile, NodeObservationProfile) for profile in self.node_profiles
        ):
            raise ValueError("architecture observation node profiles must be typed")
        if not isinstance(self.pairs, tuple) or any(not isinstance(pair, NodePairObservation) for pair in self.pairs):
            raise ValueError("architecture observation node pairs must be typed")
        if not isinstance(self.unresolved_intent_clusters, tuple) or any(
            not isinstance(cluster, UnresolvedIntentCluster) for cluster in self.unresolved_intent_clusters
        ):
            raise ValueError("architecture observation unresolved clusters must be typed")
        profile_ids = tuple(profile.node_id for profile in self.node_profiles)
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("architecture observation contains duplicate node profiles")
        pair_ids = tuple(pair.pair_id for pair in self.pairs)
        if len(pair_ids) != len(set(pair_ids)):
            raise ValueError("architecture observation contains duplicate node pairs")
        cluster_ids = tuple(cluster.cluster_id for cluster in self.unresolved_intent_clusters)
        if len(cluster_ids) != len(set(cluster_ids)):
            raise ValueError("architecture observation contains duplicate unresolved clusters")
        if self.architecture is not None:
            node_ids = set(self.architecture.node_map())
            unknown_profiles = set(profile_ids) - node_ids
            unknown_pairs = {
                node_id
                for pair in self.pairs
                for node_id in (pair.left_node_id, pair.right_node_id)
                if node_id not in node_ids
            }
            if unknown_profiles or unknown_pairs:
                raise ValueError(
                    "architecture observation references unknown nodes: "
                    f"{sorted(unknown_profiles | unknown_pairs)}"
                )
        if not isinstance(self.incident_counts, tuple):
            raise ValueError("architecture observation incident counts must be a tuple")
        for row in self.incident_counts:
            if (
                not isinstance(row, tuple)
                or len(row) != 2
                or not isinstance(row[0], str)
                or not row[0].strip()
                or isinstance(row[1], bool)
                or not isinstance(row[1], int)
                or row[1] < 0
            ):
                raise ValueError("architecture observation incident counts are invalid")
        if len({name for name, _ in self.incident_counts}) != len(self.incident_counts):
            raise ValueError("architecture observation contains duplicate incident kinds")


@dataclass(frozen=True, slots=True)
class StructuralIntent:
    edit: EditKind
    rationale: str
    payload: StructuralIntentPayload | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.edit, EditKind):
            raise ValueError("structural intent edit must be an EditKind")
        if not isinstance(self.rationale, str) or not self.rationale.strip():
            raise ValueError("structural intent rationale is required")


@dataclass(frozen=True, slots=True)
class PrimitiveEdit:
    kind: PrimitiveEditKind
    target: str
    spec: object | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, PrimitiveEditKind):
            raise ValueError("primitive edit kind must be a PrimitiveEditKind")
        if not isinstance(self.target, str) or not self.target.strip():
            raise ValueError("primitive edit target is required")


@dataclass(frozen=True, slots=True)
class CandidateArchitecture:
    base_generation: str
    candidate_id: str
    target_spec: object
    target_spec_digest: str
    primitive_edits: tuple[PrimitiveEdit, ...]
    materialization_contracts: tuple[object, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.base_generation, str) or not self.base_generation.strip():
            raise ValueError("candidate architecture base generation is required")
        if not isinstance(self.candidate_id, str) or not self.candidate_id.strip():
            raise ValueError("candidate architecture identity is required")
        if not isinstance(self.target_spec_digest, str) or not self.target_spec_digest.strip():
            raise ValueError("candidate architecture target spec digest is required")
        if not isinstance(self.primitive_edits, tuple) or any(
            not isinstance(edit, PrimitiveEdit) for edit in self.primitive_edits
        ):
            raise ValueError("candidate architecture primitive edits must be typed")
        if not isinstance(self.materialization_contracts, tuple):
            raise ValueError("candidate architecture materialization contracts must be a tuple")


@dataclass(frozen=True, slots=True)
class EvaluationProof:
    comparability: ComparabilityProof
    metrics: Mapping[str, float]

    def __post_init__(self) -> None:
        if not isinstance(self.comparability, ComparabilityProof):
            raise ValueError("evaluation proof requires a ComparabilityProof")
        if not isinstance(self.metrics, Mapping):
            raise ValueError("evaluation proof metrics must be a mapping")
        snapshot: dict[str, float] = {}
        for name, value in self.metrics.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("evaluation proof metric names must be non-empty strings")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"evaluation proof metric must be numeric: {name}")
            try:
                numeric = float(value)
            except OverflowError as exc:
                raise ValueError(f"evaluation proof metric must be finite: {name}") from exc
            if not math.isfinite(numeric):
                raise ValueError(f"evaluation proof metric must be finite: {name}")
            snapshot[name] = numeric
        object.__setattr__(self, "metrics", MappingProxyType(snapshot))


@dataclass(frozen=True, slots=True)
class EvolutionOutcome:
    status: str
    base_generation: str | None
    final_generation: str | None
    edit: EditKind | None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        allowed = {"deferred", "no_edit", "invalid_evaluation", "rejected", "adopted"}
        if self.status not in allowed:
            raise ValueError(f"unsupported evolution outcome status: {self.status!r}")
        if self.reason_code is not None and (not isinstance(self.reason_code, str) or not self.reason_code.strip()):
            raise ValueError("evolution outcome reason_code must be non-empty when present")
        if self.status == "deferred":
            if self.base_generation is not None or self.final_generation is not None or self.edit is not None:
                raise ValueError("deferred evolution outcome cannot claim a generation or edit")
            if self.reason_code is None:
                raise ValueError("deferred evolution outcome requires a reason_code")
            return
        if not isinstance(self.base_generation, str) or not self.base_generation.strip():
            raise ValueError("evolution outcome base generation is required")
        if not isinstance(self.final_generation, str) or not self.final_generation.strip():
            raise ValueError("evolution outcome final generation is required")
        if not isinstance(self.edit, EditKind):
            raise ValueError("evolution outcome edit must be typed")
        if self.status == "no_edit":
            if self.edit is not EditKind.NO_EDIT or self.final_generation != self.base_generation or self.reason_code is not None:
                raise ValueError("no_edit evolution outcome is inconsistent")
            return
        if self.edit is EditKind.NO_EDIT:
            raise ValueError("structural evolution outcome cannot carry NO_EDIT")
        if self.status in {"invalid_evaluation", "rejected"}:
            if self.final_generation != self.base_generation:
                raise ValueError("non-adopted evolution outcome cannot advance generation")
            if self.status == "invalid_evaluation" and self.reason_code is None:
                raise ValueError("invalid evaluation outcome requires a reason_code")
            if self.status == "rejected" and self.reason_code is not None:
                raise ValueError("rejected evolution outcome cannot carry an evaluation failure reason")
            return
        if self.status == "adopted":
            if self.final_generation == self.base_generation:
                raise ValueError("adopted evolution outcome must advance generation")
            if self.reason_code is not None:
                raise ValueError("adopted evolution outcome cannot carry a reason_code")


class EligibilityPort(Protocol):
    def check(self) -> EvolutionEligibility: ...


class DiagnosisPort(Protocol):
    def diagnose(self) -> ArchitectureObservationReport: ...


class SynthesisPort(Protocol):
    def propose(self, aor: ArchitectureObservationReport) -> StructuralIntent: ...


class CompilerPort(Protocol):
    def compile(self, intent: StructuralIntent, base_generation: str) -> CandidateArchitecture: ...


class EvaluatorPort(Protocol):
    def evaluate(self, candidate: CandidateArchitecture) -> EvaluationProof: ...


class AcceptancePort(Protocol):
    def accept(self, intent: StructuralIntent, proof: EvaluationProof) -> bool: ...


class AdoptionPort(Protocol):
    def adopt(self, candidate: CandidateArchitecture, proof: EvaluationProof) -> str: ...


class ContextualAdoptionPort(Protocol):
    """Pipeline adoption stage bound to the exact task execution context."""

    def adopt(
        self,
        candidate: CandidateArchitecture,
        proof: EvaluationProof,
        context: ExecutionContext | None,
    ) -> str: ...
