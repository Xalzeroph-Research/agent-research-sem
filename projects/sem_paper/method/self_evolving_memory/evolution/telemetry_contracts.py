from __future__ import annotations

"""Immutable telemetry values and bounded-state contracts."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from enum import StrEnum
import math
from types import MappingProxyType
from typing import Any

from research_platform.platform.kernel import JsonObject

from ..json_snapshot import freeze_json_mapping


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    try:
        numeric = float(value)
    except OverflowError as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not math.isfinite(numeric):
        raise ValueError(f"{label} must be finite")
    return numeric


def _snapshot_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    for key in value:
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{label} keys must be non-empty strings")
    return freeze_json_mapping(value, label=label)


class IncidentKind(StrEnum):
    STALE_USE = "STALE_USE"
    RETRIEVAL_MISS = "RETRIEVAL_MISS"
    CONFLICTING_RETRIEVAL = "CONFLICTING_RETRIEVAL"
    EXCESSIVE_RETRIEVAL_COST = "EXCESSIVE_RETRIEVAL_COST"
    UNRESOLVED_MEMORY_INTENT = "UNRESOLVED_MEMORY_INTENT"


@dataclass(frozen=True, slots=True)
class MemoryIncident:
    incident_id: str
    kind: IncidentKind
    task_id: str
    intent: str
    node_ids: tuple[str, ...]
    detail: Mapping[str, Any]

    def __post_init__(self) -> None:
        _require_text(self.incident_id, "diagnostic incident id")
        _require_text(self.task_id, "diagnostic incident task id")
        _require_text(self.intent, "diagnostic incident intent")
        if not isinstance(self.kind, IncidentKind):
            raise ValueError("diagnostic incident kind must be typed")
        if not isinstance(self.node_ids, tuple) or any(
            not isinstance(node_id, str) or not node_id.strip() for node_id in self.node_ids
        ):
            raise ValueError("diagnostic incident node ids must be non-empty strings")
        if len(self.node_ids) != len(set(self.node_ids)):
            raise ValueError("diagnostic incident node ids must be unique")
        object.__setattr__(self, "detail", _snapshot_mapping(self.detail, "diagnostic incident detail"))


@dataclass(frozen=True, slots=True)
class QueryRecordObservation:
    node_id: str
    record_id: str
    score: float = 0.0
    payload: JsonObject = field(default_factory=dict)
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.node_id, "diagnostic query record node id")
        _require_text(self.record_id, "diagnostic query record id")
        object.__setattr__(self, "score", _finite_number(self.score, "diagnostic query record score"))
        object.__setattr__(self, "payload", _snapshot_mapping(self.payload, "diagnostic query record payload"))
        if not isinstance(self.source_refs, tuple) or any(
            not isinstance(ref, str) or not ref.strip() for ref in self.source_refs
        ):
            raise ValueError("diagnostic query source refs must be non-empty strings")
        if len(self.source_refs) != len(set(self.source_refs)):
            raise ValueError("diagnostic query source refs must be unique")


@dataclass(frozen=True, slots=True)
class QueryObservation:
    query_id: str
    task_id: str
    intent: str
    opportunity_key: str | None
    selected_nodes: tuple[str, ...]
    returned_node_ids: tuple[str, ...]
    returned_record_ids: tuple[str, ...]
    top_score: float
    record_count: int
    source_ref_count: int

    def __post_init__(self) -> None:
        _require_text(self.query_id, "diagnostic query id")
        _require_text(self.task_id, "diagnostic query task id")
        _require_text(self.intent, "diagnostic query intent")
        if self.opportunity_key is not None:
            _require_text(self.opportunity_key, "diagnostic query opportunity key")
        for label, values in (
            ("selected nodes", self.selected_nodes),
            ("returned nodes", self.returned_node_ids),
            ("returned record ids", self.returned_record_ids),
        ):
            if not isinstance(values, tuple) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise ValueError(f"diagnostic query {label} must be non-empty strings")
        if len(self.returned_node_ids) != len(self.returned_record_ids):
            raise ValueError("diagnostic query returned node/record cardinality mismatch")
        if len(self.selected_nodes) != len(set(self.selected_nodes)):
            raise ValueError("diagnostic query selected nodes must be unique")
        if len(self.returned_record_ids) != len(set(self.returned_record_ids)):
            raise ValueError("diagnostic query returned records must be unique")
        for label, value in (("record_count", self.record_count), ("source_ref_count", self.source_ref_count)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"diagnostic query {label} must be a non-negative integer")
        if self.record_count != len(self.returned_record_ids):
            raise ValueError("diagnostic query record_count does not match returned records")
        object.__setattr__(self, "top_score", _finite_number(self.top_score, "diagnostic query top_score"))
        if self.record_count == 0 and (self.source_ref_count != 0 or self.top_score != 0.0):
            raise ValueError("empty diagnostic query cannot claim score or source refs")


@dataclass(frozen=True, slots=True)
class TaskObservation:
    task_id: str
    family: str
    success: bool
    utility: float
    blocked_by_prior_progress: bool = False

    def __post_init__(self) -> None:
        _require_text(self.task_id, "diagnostic task id")
        _require_text(self.family, "diagnostic task family")
        if not isinstance(self.success, bool) or not isinstance(self.blocked_by_prior_progress, bool):
            raise TypeError("diagnostic task boolean facts are invalid")
        object.__setattr__(self, "utility", _finite_number(self.utility, "diagnostic task utility"))


@dataclass(slots=True)
class NodeRuntimeStats:
    selected_count: int = 0
    result_count: int = 0
    query_count: int = 0
    empty_result_count: int = 0
    update_count: int = 0
    records_added: int = 0
    records_removed: int = 0
    full_recompute_count: int = 0
    group_recompute_count: int = 0
    score_sum: float = 0.0

    def __post_init__(self) -> None:
        count_fields = (
            "selected_count", "result_count", "query_count", "empty_result_count",
            "update_count", "records_added", "records_removed",
            "full_recompute_count", "group_recompute_count",
        )
        if any(
            isinstance(getattr(self, name), bool)
            or not isinstance(getattr(self, name), int)
            or getattr(self, name) < 0
            for name in count_fields
        ):
            raise ValueError("diagnostic node counts must be non-negative integers")
        self.score_sum = _finite_number(self.score_sum, "diagnostic node score_sum")
        if self.empty_result_count > self.query_count:
            raise ValueError("diagnostic empty-result count cannot exceed query count")
        if self.full_recompute_count > self.update_count or self.group_recompute_count > self.update_count:
            raise ValueError("diagnostic recompute count cannot exceed update count")
        if self.result_count == 0 and self.score_sum != 0.0:
            raise ValueError("diagnostic score_sum requires at least one result")

    def as_dict(self) -> dict[str, Any]:
        average = self.score_sum / self.result_count if self.result_count else 0.0
        return {**asdict(self), "avg_result_score": average}


@dataclass(frozen=True, slots=True)
class TelemetrySnapshot:
    """Immutable diagnostic cut used by probes, diagnosis, and exact resume."""

    node_stats: Mapping[str, Mapping[str, Any]]
    queries: tuple[QueryObservation, ...]
    incidents: tuple[MemoryIncident, ...]
    tasks: tuple[TaskObservation, ...]
    block_incident_cursor: int = 0
    block_query_cursor: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.node_stats, Mapping):
            raise TypeError("diagnostic node snapshot must be a mapping")
        fields = tuple(NodeRuntimeStats.__dataclass_fields__)
        frozen_stats: dict[str, Mapping[str, Any]] = {}
        for node_id, row in self.node_stats.items():
            _require_text(node_id, "diagnostic node snapshot id")
            if not isinstance(row, Mapping):
                raise ValueError("diagnostic node snapshot row must be a mapping")
            missing = tuple(name for name in fields if name not in row)
            unknown = tuple(name for name in row if name not in {*fields, "avg_result_score"})
            if missing or unknown:
                raise ValueError("diagnostic node snapshot schema mismatch")
            stats = NodeRuntimeStats(**{name: row[name] for name in fields})
            normalized = {name: getattr(stats, name) for name in fields}
            average = stats.score_sum / stats.result_count if stats.result_count else 0.0
            if "avg_result_score" in row:
                actual = _finite_number(row["avg_result_score"], "diagnostic node average score")
                if not math.isclose(actual, average, rel_tol=0.0, abs_tol=1e-12):
                    raise ValueError("diagnostic node average score does not match authoritative counts")
                normalized["avg_result_score"] = actual
            frozen_stats[node_id] = MappingProxyType(normalized)
        object.__setattr__(self, "node_stats", MappingProxyType(frozen_stats))
        for label, values, expected in (
            ("queries", self.queries, QueryObservation),
            ("incidents", self.incidents, MemoryIncident),
            ("tasks", self.tasks, TaskObservation),
        ):
            if not isinstance(values, tuple) or any(not isinstance(row, expected) for row in values):
                raise ValueError(f"diagnostic snapshot {label} must be a typed tuple")
        query_ids = tuple(row.query_id for row in self.queries)
        incident_ids = tuple(row.incident_id for row in self.incidents)
        task_ids = tuple(row.task_id for row in self.tasks)
        if len(set(query_ids)) != len(query_ids):
            raise ValueError("diagnostic snapshot contains duplicate query ids")
        if len(set(incident_ids)) != len(incident_ids):
            raise ValueError("diagnostic snapshot contains duplicate incident ids")
        if len(set(task_ids)) != len(task_ids):
            raise ValueError("diagnostic snapshot contains duplicate task ids")
        for label, cursor, size in (
            ("incident", self.block_incident_cursor, len(self.incidents)),
            ("query", self.block_query_cursor, len(self.queries)),
        ):
            if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0 or cursor > size:
                raise ValueError(f"diagnostic {label} cursor is outside the snapshot")


class TelemetryCapacityExceeded(RuntimeError):
    """Fail-closed guard against unbounded scientific diagnostic state."""


@dataclass(frozen=True, slots=True)
class TelemetryLimits:
    max_nodes: int = 4096
    max_queries: int = 65536
    max_incidents: int = 131072
    max_tasks: int = 16384

    def __post_init__(self) -> None:
        values = (self.max_nodes, self.max_queries, self.max_incidents, self.max_tasks)
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in values):
            raise ValueError("diagnostic telemetry limits must be positive integers")


__all__ = [
    "IncidentKind", "MemoryIncident", "NodeRuntimeStats", "QueryObservation",
    "QueryRecordObservation", "TaskObservation", "TelemetryCapacityExceeded",
    "TelemetryLimits", "TelemetrySnapshot",
]
