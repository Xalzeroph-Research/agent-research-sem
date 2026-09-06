from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
import math
from types import MappingProxyType


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _require_text_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{label} must be a tuple")
    for item in value:
        _require_text(item, f"{label} entry")
    if len(value) != len(set(value)):
        raise ValueError(f"{label} entries must be unique")
    return value


def _require_int(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _require_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    try:
        numeric = float(value)
    except OverflowError as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not math.isfinite(numeric):
        raise ValueError(f"{label} must be finite")
    return numeric


def _require_sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ValueError(f"{label} must be a lower-case SHA-256 digest")
    return value


class MemoryRuntimeTier(StrEnum):
    CORE = "core"
    STANDARD = "standard"
    DELUXE = "deluxe"


@dataclass(frozen=True, slots=True)
class DeluxeNodeDescriptor:
    """Read-only projection of one node in the current method architecture."""

    node_id: str
    purpose: str
    access: tuple[str, ...] = ()
    output_types: tuple[str, ...] = ()
    scope: str = "session"

    def __post_init__(self) -> None:
        _require_text(self.node_id, "Deluxe node_id")
        _require_text(self.purpose, "Deluxe node purpose")
        _require_text(self.scope, "Deluxe node scope")
        _require_text_tuple(self.access, "Deluxe node access")
        _require_text_tuple(self.output_types, "Deluxe node output_types")


@dataclass(frozen=True, slots=True)
class DeluxeArchitectureSnapshot:
    """Pinned architecture read model used to derive capabilities.

    The snapshot is not an architecture-head writer. Its digest and generation
    must come from the method's authoritative architecture state.
    """

    generation: str
    digest: str
    nodes: tuple[DeluxeNodeDescriptor, ...]
    generation_number: int = 0

    def __post_init__(self) -> None:
        _require_text(self.generation, "Deluxe architecture generation")
        _require_sha256(self.digest, "Deluxe architecture digest")
        _require_int(self.generation_number, "Deluxe architecture generation_number")
        if not isinstance(self.nodes, tuple) or any(not isinstance(node, DeluxeNodeDescriptor) for node in self.nodes):
            raise ValueError("Deluxe architecture nodes must be typed")
        node_ids = tuple(node.node_id for node in self.nodes)
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Deluxe architecture node ids must be unique")


class CapabilityState(StrEnum):
    PROBATION = "PROBATION"
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"
    RETIRE_CANDIDATE = "RETIRE_CANDIDATE"


@dataclass(frozen=True, slots=True)
class CapabilityCard:
    capability_id: str
    provider_node_id: str
    purpose: str
    access: tuple[str, ...]
    output_types: tuple[str, ...]
    scope: str
    generation_created: str

    def __post_init__(self) -> None:
        for label, value in (
            ("capability_id", self.capability_id),
            ("provider_node_id", self.provider_node_id),
            ("purpose", self.purpose),
            ("scope", self.scope),
            ("generation_created", self.generation_created),
        ):
            _require_text(value, f"Deluxe capability {label}")
        _require_text_tuple(self.access, "Deluxe capability access")
        _require_text_tuple(self.output_types, "Deluxe capability output_types")

    @property
    def semantic_card(self) -> str:
        return " ".join((self.purpose, self.scope, *self.access, *self.output_types))


@dataclass(slots=True)
class CapabilityLifecycle:
    state: CapabilityState = CapabilityState.ACTIVE
    age_queries: int = 0
    selected_queries: int = 0
    useful_queries: int = 0
    last_selected_query: int = -1
    probation_queries_remaining: int = 0
    lease_queries_remaining: int = 0
    utility_ema: float = 0.0

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not isinstance(self.state, CapabilityState):
            raise ValueError("Deluxe capability lifecycle state must be typed")
        for label, value in (
            ("age_queries", self.age_queries),
            ("selected_queries", self.selected_queries),
            ("useful_queries", self.useful_queries),
            ("probation_queries_remaining", self.probation_queries_remaining),
            ("lease_queries_remaining", self.lease_queries_remaining),
        ):
            _require_int(value, f"Deluxe capability lifecycle {label}")
        _require_int(self.last_selected_query, "Deluxe capability lifecycle last_selected_query", minimum=-1)
        if self.useful_queries > self.selected_queries:
            raise ValueError("Deluxe useful_queries cannot exceed selected_queries")
        self.utility_ema = _require_float(self.utility_ema, "Deluxe capability lifecycle utility_ema")

    def usefulness_rate(self) -> float:
        return self.useful_queries / max(1, self.selected_queries)


@dataclass(frozen=True, slots=True)
class CapabilityLifecycleConfig:
    probation_queries: int = 12
    lease_queries: int = 80
    dormant_after_queries: int = 40
    min_probation_selections: int = 2
    min_probation_usefulness: float = 0.20
    retire_after_dormant_queries: int = 80

    def __post_init__(self) -> None:
        for label, value in (
            ("probation_queries", self.probation_queries),
            ("lease_queries", self.lease_queries),
            ("dormant_after_queries", self.dormant_after_queries),
            ("min_probation_selections", self.min_probation_selections),
            ("retire_after_dormant_queries", self.retire_after_dormant_queries),
        ):
            _require_int(value, f"Deluxe lifecycle config {label}", minimum=1)
        usefulness = _require_float(self.min_probation_usefulness, "Deluxe min_probation_usefulness")
        if not 0.0 <= usefulness <= 1.0:
            raise ValueError("Deluxe probation usefulness must be in [0,1]")
        object.__setattr__(self, "min_probation_usefulness", usefulness)


@dataclass(frozen=True, slots=True)
class QueryBudget:
    node_limit: int
    record_limit: int
    token_budget: int
    exploration_slots: int = 0

    def __post_init__(self) -> None:
        _require_int(self.node_limit, "Deluxe query node_limit", minimum=1)
        _require_int(self.record_limit, "Deluxe query record_limit", minimum=1)
        _require_int(self.token_budget, "Deluxe query token_budget", minimum=1)
        _require_int(self.exploration_slots, "Deluxe query exploration_slots")
        if self.exploration_slots > self.node_limit:
            raise ValueError("Deluxe exploration_slots must fit node_limit")


@dataclass(frozen=True, slots=True)
class BudgetPolicyConfig:
    default_nodes: int = 3
    default_records: int = 8
    default_tokens: int = 1800
    min_nodes: int = 1
    max_nodes: int = 8
    min_records: int = 2
    max_records: int = 24
    exploration_fraction: float = 0.20
    per_node_record_cap: int = 8
    probation_budget_scale: float = 0.60

    def __post_init__(self) -> None:
        for label, value in (
            ("default_nodes", self.default_nodes), ("default_records", self.default_records),
            ("default_tokens", self.default_tokens), ("min_nodes", self.min_nodes),
            ("max_nodes", self.max_nodes), ("min_records", self.min_records),
            ("max_records", self.max_records), ("per_node_record_cap", self.per_node_record_cap),
        ):
            _require_int(value, f"Deluxe budget config {label}", minimum=1)
        if self.min_nodes > self.max_nodes or self.min_records > self.max_records:
            raise ValueError("Deluxe budget minimum cannot exceed maximum")
        if not self.min_nodes <= self.default_nodes <= self.max_nodes:
            raise ValueError("Deluxe default_nodes must be within configured bounds")
        if not self.min_records <= self.default_records <= self.max_records:
            raise ValueError("Deluxe default_records must be within configured bounds")
        exploration = _require_float(self.exploration_fraction, "Deluxe exploration_fraction")
        probation_scale = _require_float(self.probation_budget_scale, "Deluxe probation_budget_scale")
        if not 0.0 <= exploration <= 1.0:
            raise ValueError("Deluxe exploration_fraction must be in [0,1]")
        if not 0.0 < probation_scale <= 1.0:
            raise ValueError("Deluxe probation_budget_scale must be in (0,1]")
        object.__setattr__(self, "exploration_fraction", exploration)
        object.__setattr__(self, "probation_budget_scale", probation_scale)


@dataclass(frozen=True, slots=True)
class WorkingSetEntry:
    capability_id: str
    node_id: str
    score: float
    exploration: bool = False

    def __post_init__(self) -> None:
        _require_text(self.capability_id, "Deluxe working-set capability_id")
        _require_text(self.node_id, "Deluxe working-set node_id")
        object.__setattr__(self, "score", _require_float(self.score, "Deluxe working-set score"))
        if not isinstance(self.exploration, bool):
            raise ValueError("Deluxe working-set exploration must be boolean")


@dataclass(frozen=True, slots=True)
class WorkingSet:
    entries: tuple[WorkingSetEntry, ...]
    budget_nodes: int

    def __post_init__(self) -> None:
        _require_int(self.budget_nodes, "Deluxe working-set budget_nodes", minimum=1)
        if not isinstance(self.entries, tuple) or any(not isinstance(entry, WorkingSetEntry) for entry in self.entries):
            raise ValueError("Deluxe working-set entries must be typed")
        ids = tuple(entry.capability_id for entry in self.entries)
        if len(ids) != len(set(ids)):
            raise ValueError("Deluxe working set cannot contain duplicate capabilities")
        if len(self.entries) > self.budget_nodes:
            raise ValueError("Deluxe working set exceeds its node budget")

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(entry.node_id for entry in self.entries)

    @property
    def capability_ids(self) -> tuple[str, ...]:
        return tuple(entry.capability_id for entry in self.entries)


@dataclass(frozen=True, slots=True)
class WorkingSetPolicyConfig:
    relevance_weight: float = 1.0
    utility_weight: float = 0.20
    reliability_weight: float = 0.15
    cost_weight: float = 0.10
    exploration_bonus: float = 0.05

    def __post_init__(self) -> None:
        for field_name in ("relevance_weight", "utility_weight", "reliability_weight", "cost_weight", "exploration_bonus"):
            value = _require_float(getattr(self, field_name), f"Deluxe working-set {field_name}")
            if value < 0.0:
                raise ValueError(f"Deluxe working-set {field_name} must be non-negative")
            object.__setattr__(self, field_name, value)


@dataclass(frozen=True, slots=True)
class MemoryFault:
    fault_id: str
    intent: str
    missing_capability_id: str
    missing_node_id: str
    reason: str
    recovered: bool

    def __post_init__(self) -> None:
        for label, value in (
            ("fault_id", self.fault_id), ("intent", self.intent),
            ("missing_capability_id", self.missing_capability_id),
            ("missing_node_id", self.missing_node_id), ("reason", self.reason),
        ):
            _require_text(value, f"Deluxe memory fault {label}")
        if not isinstance(self.recovered, bool):
            raise ValueError("Deluxe memory fault recovered must be boolean")


@dataclass(frozen=True, slots=True)
class LineageEdge:
    source_ref: str
    derived_ref: str
    relation: str

    def __post_init__(self) -> None:
        _require_text(self.source_ref, "Deluxe lineage source_ref")
        _require_text(self.derived_ref, "Deluxe lineage derived_ref")
        _require_text(self.relation, "Deluxe lineage relation")


@dataclass(frozen=True, slots=True)
class MemoryLineageRecord:
    record_id: str
    generation: str
    source_refs: tuple[str, ...] = ()
    attributes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.record_id, "Deluxe lineage record_id")
        _require_text(self.generation, "Deluxe lineage generation")
        _require_text_tuple(self.source_refs, "Deluxe lineage source_refs")
        if not isinstance(self.attributes, Mapping):
            raise ValueError("Deluxe lineage attributes must be a mapping")
        snapshot: dict[str, str] = {}
        for key, value in self.attributes.items():
            _require_text(key, "Deluxe lineage attribute key")
            if not isinstance(value, str):
                raise ValueError("Deluxe lineage attribute values must be strings")
            snapshot[key] = value
        object.__setattr__(self, "attributes", MappingProxyType(snapshot))


__all__ = [
    "BudgetPolicyConfig",
    "CapabilityCard",
    "CapabilityLifecycle",
    "CapabilityLifecycleConfig",
    "CapabilityState",
    "DeluxeArchitectureSnapshot",
    "DeluxeNodeDescriptor",
    "LineageEdge",
    "MemoryFault",
    "MemoryLineageRecord",
    "MemoryRuntimeTier",
    "QueryBudget",
    "WorkingSet",
    "WorkingSetEntry",
    "WorkingSetPolicyConfig",
]
