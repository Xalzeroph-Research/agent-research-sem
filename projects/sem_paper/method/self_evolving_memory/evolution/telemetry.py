from __future__ import annotations

"""Session-owned diagnostic telemetry mutation authority."""

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Any, Mapping, Protocol, Sequence

from .telemetry_contracts import (
    IncidentKind,
    MemoryIncident,
    NodeRuntimeStats,
    QueryObservation,
    QueryRecordObservation,
    TaskObservation,
    TelemetryCapacityExceeded,
    TelemetryLimits,
    TelemetrySnapshot,
)


class DiagnosticTelemetryPort(Protocol):
    """Write/read seam; storage and platform sinks remain injected."""

    def record_query(
        self,
        *,
        task_id: str,
        intent: str,
        opportunity_key: str | None,
        selected_nodes: Sequence[str],
        records: Sequence[QueryRecordObservation],
        max_reasonable_nodes: int = 3,
        min_useful_score: float = 0.05,
    ) -> QueryObservation: ...

    def record_task(self, observation: TaskObservation) -> None: ...

    def snapshot(self) -> TelemetrySnapshot: ...

    def restore(self, snapshot: TelemetrySnapshot) -> None: ...


@dataclass(slots=True)
class TelemetryBook:
    """Bounded-domain diagnostic book with explicit immutable read cuts.

    This object is not the platform telemetry sink.  It is a project-local
    diagnostic projection that can be rebuilt from the platform observations.
    No method-memory write or architecture mutation is exposed here.
    """

    node_stats: dict[str, NodeRuntimeStats] = field(default_factory=dict)
    queries: list[QueryObservation] = field(default_factory=list)
    incidents: list[MemoryIncident] = field(default_factory=list)
    tasks: list[TaskObservation] = field(default_factory=list)
    limits: TelemetryLimits = field(default_factory=TelemetryLimits)
    _block_incident_cursor: int = 0
    _block_query_cursor: int = 0
    _task_by_id: dict[str, TaskObservation] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.limits, TelemetryLimits):
            raise TypeError("diagnostic telemetry limits must be typed")
        if not isinstance(self.node_stats, dict) or any(
            not isinstance(node_id, str) or not node_id.strip() or not isinstance(stats, NodeRuntimeStats)
            for node_id, stats in self.node_stats.items()
        ):
            raise ValueError("diagnostic node state must be a typed node-id mapping")
        for label, values, expected in (
            ("queries", self.queries, QueryObservation),
            ("incidents", self.incidents, MemoryIncident),
            ("tasks", self.tasks, TaskObservation),
        ):
            if not isinstance(values, list) or any(not isinstance(row, expected) for row in values):
                raise ValueError(f"diagnostic {label} state must be a typed list")
        for label, cursor, size in (
            ("incident", self._block_incident_cursor, len(self.incidents)),
            ("query", self._block_query_cursor, len(self.queries)),
        ):
            if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0 or cursor > size:
                raise ValueError(f"diagnostic {label} cursor is outside current state")
        if len(self.node_stats) > self.limits.max_nodes:
            raise TelemetryCapacityExceeded("diagnostic node capacity exceeded")
        if len(self.queries) > self.limits.max_queries:
            raise TelemetryCapacityExceeded("diagnostic query capacity exceeded")
        if len(self.incidents) > self.limits.max_incidents:
            raise TelemetryCapacityExceeded("diagnostic incident capacity exceeded")
        if len(self.tasks) > self.limits.max_tasks:
            raise TelemetryCapacityExceeded("diagnostic task capacity exceeded")
        for rows, label, identity in (
            (self.queries, "query", lambda row: row.query_id),
            (self.incidents, "incident", lambda row: row.incident_id),
            (self.tasks, "task", lambda row: row.task_id),
        ):
            ids = tuple(identity(row) for row in rows)
            if len(ids) != len(set(ids)):
                raise ValueError(f"diagnostic {label} state contains duplicate ids")
        fields = tuple(NodeRuntimeStats.__dataclass_fields__)
        self.node_stats = {
            node_id: NodeRuntimeStats(**{name: getattr(stats, name) for name in fields})
            for node_id, stats in self.node_stats.items()
        }
        self.queries = list(self.queries)
        self.incidents = list(self.incidents)
        self.tasks = list(self.tasks)
        self._task_by_id = {observation.task_id: observation for observation in self.tasks}

    def _node(self, node_id: str) -> NodeRuntimeStats:
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("diagnostic node id must be a non-empty string")
        return self.node_stats.setdefault(node_id, NodeRuntimeStats())

    def record_query(
        self,
        *,
        task_id: str,
        intent: str,
        opportunity_key: str | None,
        selected_nodes: Sequence[str],
        records: Sequence[QueryRecordObservation],
        max_reasonable_nodes: int = 3,
        min_useful_score: float = 0.05,
    ) -> QueryObservation:
        if not isinstance(task_id, str) or not task_id.strip() or not isinstance(intent, str) or not intent.strip():
            raise ValueError("diagnostic query task_id and intent must be non-empty strings")
        if opportunity_key is not None and (not isinstance(opportunity_key, str) or not opportunity_key.strip()):
            raise ValueError("diagnostic query opportunity_key must be a non-empty string when present")
        if isinstance(max_reasonable_nodes, bool) or not isinstance(max_reasonable_nodes, int) or max_reasonable_nodes < 0:
            raise ValueError("diagnostic max_reasonable_nodes must be a non-negative integer")
        if isinstance(min_useful_score, bool) or not isinstance(min_useful_score, (int, float)):
            raise ValueError("diagnostic min_useful_score must be numeric")
        try:
            useful_score = float(min_useful_score)
        except OverflowError as exc:
            raise ValueError("diagnostic min_useful_score must be finite") from exc
        if not math.isfinite(useful_score):
            raise ValueError("diagnostic min_useful_score must be finite")
        if len(self.queries) >= self.limits.max_queries:
            raise TelemetryCapacityExceeded("diagnostic query capacity exceeded")

        if isinstance(selected_nodes, (str, bytes)) or not isinstance(selected_nodes, Sequence):
            raise ValueError("diagnostic selected_nodes must be a sequence of node ids")
        selected = tuple(selected_nodes)
        if any(not isinstance(node_id, str) or not node_id.strip() for node_id in selected):
            raise ValueError("diagnostic selected node ids must be non-empty strings")
        if len(selected) != len(set(selected)):
            raise ValueError("diagnostic selected node ids must be unique")
        if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
            raise ValueError("diagnostic records must be a sequence")
        normalized_records = tuple(records)
        if any(not isinstance(record, QueryRecordObservation) for record in normalized_records):
            raise ValueError("diagnostic records must contain typed query record observations")
        record_ids = tuple(record.record_id for record in normalized_records)
        if len(set(record_ids)) != len(record_ids):
            raise ValueError("diagnostic query records must have unique identities")
        returned_nodes = tuple(record.node_id for record in normalized_records)
        touched = set(selected) | set(returned_nodes)
        new_nodes = {node_id for node_id in touched if node_id not in self.node_stats}
        if len(self.node_stats) + len(new_nodes) > self.limits.max_nodes:
            raise TelemetryCapacityExceeded("diagnostic node capacity exceeded")

        query_id = "qry_" + hashlib.sha256(
            json.dumps(
                [task_id, intent, len(self.queries)],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:16]
        scores = tuple(float(record.score) for record in normalized_records)
        observation = QueryObservation(
            query_id=query_id,
            task_id=task_id,
            intent=intent,
            opportunity_key=opportunity_key,
            selected_nodes=selected,
            returned_node_ids=returned_nodes,
            returned_record_ids=record_ids,
            top_score=max(scores, default=0.0),
            record_count=len(normalized_records),
            source_ref_count=sum(len(record.source_refs) for record in normalized_records),
        )

        incident_specs: list[tuple[IncidentKind, tuple[str, ...], dict[str, Any]]] = []
        if opportunity_key and not normalized_records:
            incident_specs.extend(
                (
                    (IncidentKind.RETRIEVAL_MISS, selected, {"query_id": query_id}),
                    (
                        IncidentKind.UNRESOLVED_MEMORY_INTENT,
                        selected,
                        {"query_id": query_id, "reason": "no_result"},
                    ),
                )
            )
        elif opportunity_key and scores and max(scores) < useful_score:
            incident_specs.append(
                (
                    IncidentKind.UNRESOLVED_MEMORY_INTENT,
                    selected,
                    {"query_id": query_id, "reason": "low_score", "top_score": max(scores)},
                )
            )
        if len(selected) > max_reasonable_nodes:
            incident_specs.append(
                (
                    IncidentKind.EXCESSIVE_RETRIEVAL_COST,
                    selected,
                    {"query_id": query_id, "selected_nodes": len(selected)},
                )
            )
        scalar_values: dict[str, set[str]] = {}
        for record in normalized_records:
            for key, value in record.payload.items():
                if isinstance(value, (str, int, float, bool)):
                    scalar_values.setdefault(str(key), set()).add(repr(value))
        conflicts = {key: sorted(values) for key, values in scalar_values.items() if len(values) >= 3}
        if conflicts:
            incident_specs.append(
                (
                    IncidentKind.CONFLICTING_RETRIEVAL,
                    tuple(sorted(set(returned_nodes))),
                    {"query_id": query_id, "fields": conflicts},
                )
            )
        if len(self.incidents) + len(incident_specs) > self.limits.max_incidents:
            raise TelemetryCapacityExceeded("diagnostic incident capacity exceeded")

        self.queries.append(observation)
        for node_id in selected:
            stats = self._node(node_id)
            stats.query_count += 1
            stats.selected_count += 1
        if not normalized_records:
            for node_id in selected:
                self._node(node_id).empty_result_count += 1
        for record in normalized_records:
            stats = self._node(record.node_id)
            stats.result_count += 1
            stats.score_sum += record.score
        for kind, node_ids, detail in incident_specs:
            self._append_incident(kind, task_id, intent, node_ids, detail)
        return observation

    def record_node_update(
        self,
        node_id: str,
        *,
        records_added: int = 0,
        records_removed: int = 0,
        full_recompute: bool = False,
        group_recompute: bool = False,
    ) -> None:
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("diagnostic node id must be a non-empty string")
        values = (records_added, records_removed)
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
            raise ValueError("diagnostic node update counts must be non-negative integers")
        if not isinstance(full_recompute, bool) or not isinstance(group_recompute, bool):
            raise TypeError("diagnostic recompute flags must be booleans")
        if node_id not in self.node_stats and len(self.node_stats) >= self.limits.max_nodes:
            raise TelemetryCapacityExceeded("diagnostic node capacity exceeded")
        stats = self._node(node_id)
        stats.update_count += 1
        stats.records_added += records_added
        stats.records_removed += records_removed
        stats.full_recompute_count += int(full_recompute)
        stats.group_recompute_count += int(group_recompute)

    def record_task(self, observation: TaskObservation) -> None:
        """Record a task exactly once; retries must replay the same scientific fact."""

        if not isinstance(observation, TaskObservation):
            raise TypeError("diagnostic task observation must be typed")
        current = self._task_by_id.get(observation.task_id)
        if current is not None:
            if current != observation:
                raise ValueError(
                    f"diagnostic task outcome drift for completed task: {observation.task_id}"
                )
            return
        if len(self.tasks) >= self.limits.max_tasks:
            raise TelemetryCapacityExceeded("diagnostic task capacity exceeded")
        self.tasks.append(observation)
        self._task_by_id[observation.task_id] = observation

    def _append_incident(
        self,
        kind: IncidentKind,
        task_id: str,
        intent: str,
        node_ids: tuple[str, ...],
        detail: Mapping[str, Any],
    ) -> None:
        raw = json.dumps(
            [kind.value, task_id, intent, len(self.incidents)],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        incident_id = "inc_" + hashlib.sha256(raw).hexdigest()[:16]
        self.incidents.append(
            MemoryIncident(incident_id, kind, task_id, intent, tuple(node_ids), dict(detail))
        )

    def block_delta(self) -> tuple[tuple[MemoryIncident, ...], tuple[QueryObservation, ...]]:
        incidents = tuple(self.incidents[self._block_incident_cursor :])
        queries = tuple(self.queries[self._block_query_cursor :])
        self._block_incident_cursor = len(self.incidents)
        self._block_query_cursor = len(self.queries)
        return incidents, queries

    def snapshot(self) -> TelemetrySnapshot:
        return TelemetrySnapshot(
            node_stats={node_id: stats.as_dict() for node_id, stats in sorted(self.node_stats.items())},
            queries=tuple(self.queries),
            incidents=tuple(self.incidents),
            tasks=tuple(self.tasks),
            block_incident_cursor=self._block_incident_cursor,
            block_query_cursor=self._block_query_cursor,
        )

    def restore(self, snapshot: TelemetrySnapshot) -> None:
        """Restore an immutable diagnostic cut without replaying synthetic observations."""

        if not isinstance(snapshot, TelemetrySnapshot):
            raise TypeError("diagnostic restore requires a TelemetrySnapshot")
        if len(snapshot.node_stats) > self.limits.max_nodes:
            raise TelemetryCapacityExceeded("diagnostic node capacity exceeded by snapshot")
        if len(snapshot.queries) > self.limits.max_queries:
            raise TelemetryCapacityExceeded("diagnostic query capacity exceeded by snapshot")
        if len(snapshot.incidents) > self.limits.max_incidents:
            raise TelemetryCapacityExceeded("diagnostic incident capacity exceeded by snapshot")
        if len(snapshot.tasks) > self.limits.max_tasks:
            raise TelemetryCapacityExceeded("diagnostic task capacity exceeded by snapshot")

        restored_stats: dict[str, NodeRuntimeStats] = {}
        fields = tuple(NodeRuntimeStats.__dataclass_fields__)
        for node_id, row in snapshot.node_stats.items():
            values = {name: row[name] for name in fields}
            restored_stats[node_id] = NodeRuntimeStats(**values)
        self.node_stats = restored_stats
        self.queries = list(snapshot.queries)
        self.incidents = list(snapshot.incidents)
        self.tasks = list(snapshot.tasks)
        self._task_by_id = {row.task_id: row for row in snapshot.tasks}
        self._block_incident_cursor = snapshot.block_incident_cursor
        self._block_query_cursor = snapshot.block_query_cursor
