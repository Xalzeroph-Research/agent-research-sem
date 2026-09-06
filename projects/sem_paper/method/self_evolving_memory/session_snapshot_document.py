from __future__ import annotations

from dataclasses import asdict
from typing import Any

from research_platform.platform.kernel import ExecutionContext
from research_platform.participant.method.api import MethodObservation

from .evidence_api import EvidenceRecord, EvidenceSnapshot
from .json_snapshot import thaw_json, thaw_json_mapping
from .evolution import (
    IncidentKind,
    MemoryIncident,
    QueryObservation,
    TaskObservation,
    TelemetrySnapshot,
)
from .session_reducer import SEMSessionState
from .serving import ServingRuntimeState
from .session_snapshot_contracts import SEMSessionStateSnapshot, SEMSnapshotPayload, SessionLineageSnapshot, SessionMutationRecord
from .task_lifecycle import TaskPhase, TaskProgress


def snapshot_document(payload: SEMSnapshotPayload) -> dict[str, Any]:
    session_state = payload.session_state
    return {
        "state": asdict(session_state.state),
        "lineage": {
            "revision": session_state.lineage.revision,
            "mutation_tail": [asdict(row) for row in session_state.lineage.mutation_tail],
        },
        "task_progress": [
            {
                "task_key": row.task_key,
                "phase": row.phase.value,
                "base_generation": row.base_generation,
                "final_generation": row.final_generation,
                "terminal_reason": row.terminal_reason,
            }
            for row in payload.task_progress
        ],
        "pending_observations": [
            {
                "observation_id": row.observation_id,
                "context": asdict(row.context),
                "method_id": row.method_id,
                "session_id": row.session_id,
                "kind": row.kind,
                "payload": dict(row.payload),
            }
            for row in payload.pending_observations
        ],
        "evolution_telemetry": {
            "node_stats": {
                str(node_id): dict(row)
                for node_id, row in sorted(payload.evolution_telemetry.node_stats.items())
            },
            "queries": [asdict(row) for row in payload.evolution_telemetry.queries],
            "incidents": [
                {
                    "incident_id": row.incident_id,
                    "kind": row.kind.value,
                    "task_id": row.task_id,
                    "intent": row.intent,
                    "node_ids": list(row.node_ids),
                    "detail": thaw_json_mapping(row.detail),
                }
                for row in payload.evolution_telemetry.incidents
            ],
            "tasks": [asdict(row) for row in payload.evolution_telemetry.tasks],
            "block_incident_cursor": payload.evolution_telemetry.block_incident_cursor,
            "block_query_cursor": payload.evolution_telemetry.block_query_cursor,
        },
        "serving_state": {
            "state_kind": payload.serving_state.state_kind,
            "schema_version": payload.serving_state.schema_version,
            "payload": thaw_json_mapping(payload.serving_state.payload),
        },
        "evidence": {
            "sequence": session_state.evidence.sequence,
            "digest": session_state.evidence.digest,
            "rows": [
                {
                    "evidence_id": row.evidence_id,
                    "sequence": row.sequence,
                    "payload": thaw_json(row.payload),
                    "digest": row.digest,
                }
                for row in session_state.evidence.rows
            ],
        },
    }


def _require_dict(value: object, label: str, fields: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    if fields is not None and set(value) != fields:
        raise ValueError(f"{label} fields are not exact")
    return value


def _require_list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _require_text(value: object, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(f"{label} must be a {'string' if allow_empty else 'non-empty string'}")
    return value


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, label)


def _require_int(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _require_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def _require_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _require_string_array(value: object, label: str) -> tuple[str, ...]:
    rows = _require_list(value, label)
    result = tuple(_require_text(item, f"{label} item") for item in rows)
    return result


def _decode_context(value: object) -> ExecutionContext:
    fields = set(ExecutionContext.__dataclass_fields__)
    row = _require_dict(value, "SEM observation context", fields)
    values = dict(row)
    for name in ("run_id", "trace_id", "span_id"):
        values[name] = _require_text(row[name], f"SEM observation context {name}")
    for name in (
        "parent_span_id", "study_id", "condition_id", "lifetime_id", "branch_id", "task_id",
        "decision_cycle_id", "checkpoint_id", "operation_id", "component_id", "platform_generation",
    ):
        values[name] = _optional_text(row[name], f"SEM observation context {name}")
    raw_generations = _require_list(row["participant_generations"], "SEM participant generations")
    generations: list[tuple[str, str]] = []
    for item in raw_generations:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError("SEM participant generation entry must be a two-item array")
        generations.append(
            (
                _require_text(item[0], "SEM participant generation role"),
                _require_text(item[1], "SEM participant generation value"),
            )
        )
    values["participant_generations"] = tuple(generations)
    return ExecutionContext(**values)


def _decode_mutation(value: object) -> SessionMutationRecord:
    fields = set(SessionMutationRecord.__dataclass_fields__)
    row = _require_dict(value, "SEM mutation record", fields)
    return SessionMutationRecord(
        revision=_require_int(row["revision"], "SEM mutation revision", minimum=1),
        mutation_type=_require_text(row["mutation_type"], "SEM mutation type"),
        before_state_digest=_require_text(row["before_state_digest"], "SEM before state digest"),
        after_state_digest=_require_text(row["after_state_digest"], "SEM after state digest"),
        before_evidence_digest=_require_text(row["before_evidence_digest"], "SEM before evidence digest"),
        after_evidence_digest=_require_text(row["after_evidence_digest"], "SEM after evidence digest"),
        before_closed=_require_bool(row["before_closed"], "SEM mutation before_closed"),
        after_closed=_require_bool(row["after_closed"], "SEM mutation after_closed"),
        evidence_sequence=_require_int(row["evidence_sequence"], "SEM mutation evidence sequence"),
        architecture_generation=_require_text(row["architecture_generation"], "SEM mutation architecture generation"),
        source_revision=(None if row["source_revision"] is None else _require_int(row["source_revision"], "SEM mutation source revision")),
        run_id=_optional_text(row["run_id"], "SEM mutation run_id"),
        task_id=_optional_text(row["task_id"], "SEM mutation task_id"),
        decision_cycle_id=_optional_text(row["decision_cycle_id"], "SEM mutation decision_cycle_id"),
        operation_id=_optional_text(row["operation_id"], "SEM mutation operation_id"),
        trace_id=_optional_text(row["trace_id"], "SEM mutation trace_id"),
        span_id=_optional_text(row["span_id"], "SEM mutation span_id"),
    )


def _decode_state(value: object) -> SEMSessionState:
    row = _require_dict(value, "SEM state", set(SEMSessionState.__dataclass_fields__))
    return SEMSessionState(
        architecture_generation=_require_text(row["architecture_generation"], "SEM architecture generation"),
        evidence_sequence=_require_int(row["evidence_sequence"], "SEM evidence sequence"),
        evolution_epoch=_require_int(row["evolution_epoch"], "SEM evolution epoch"),
        tasks_completed=_require_int(row["tasks_completed"], "SEM tasks completed"),
        last_grounded_payload=_require_text(row["last_grounded_payload"], "SEM last grounded payload", allow_empty=True),
    )


def _decode_evidence(value: object) -> EvidenceSnapshot:
    data = _require_dict(value, "SEM evidence", {"sequence", "digest", "rows"})
    rows: list[EvidenceRecord] = []
    for item in _require_list(data["rows"], "SEM evidence rows"):
        row = _require_dict(item, "SEM evidence row", {"evidence_id", "sequence", "payload", "digest"})
        rows.append(EvidenceRecord(
            evidence_id=_require_text(row["evidence_id"], "SEM evidence id"),
            sequence=_require_int(row["sequence"], "SEM evidence row sequence", minimum=1),
            payload=row["payload"],
            digest=_require_text(row["digest"], "SEM evidence row digest"),
        ))
    return EvidenceSnapshot(
        sequence=_require_int(data["sequence"], "SEM evidence snapshot sequence"),
        rows=tuple(rows),
        digest=_require_text(data["digest"], "SEM evidence snapshot digest"),
    )


def _decode_lineage(value: object) -> SessionLineageSnapshot:
    data = _require_dict(value, "SEM lineage", {"revision", "mutation_tail"})
    return SessionLineageSnapshot(
        revision=_require_int(data["revision"], "SEM lineage revision"),
        mutation_tail=tuple(
            _decode_mutation(row)
            for row in _require_list(data["mutation_tail"], "SEM mutation tail")
        ),
    )


def _decode_pending(value: object) -> tuple[MethodObservation, ...]:
    fields = {"observation_id", "context", "method_id", "session_id", "kind", "payload"}
    result: list[MethodObservation] = []
    for item in _require_list(value, "SEM pending observations"):
        row = _require_dict(item, "SEM pending observation", fields)
        payload = _require_dict(row["payload"], "SEM pending observation payload")
        result.append(MethodObservation(
            _require_text(row["observation_id"], "SEM observation id"),
            _decode_context(row["context"]),
            _require_text(row["method_id"], "SEM observation method_id"),
            _require_text(row["session_id"], "SEM observation session_id"),
            _require_text(row["kind"], "SEM observation kind"),
            dict(payload),
        ))
    return tuple(result)


def _decode_task_progress(value: object) -> tuple[TaskProgress, ...]:
    fields = {"task_key", "phase", "base_generation", "final_generation", "terminal_reason"}
    result: list[TaskProgress] = []
    for item in _require_list(value, "SEM task progress"):
        row = _require_dict(item, "SEM task progress row", fields)
        result.append(TaskProgress(
            task_key=_require_text(row["task_key"], "SEM task key"),
            phase=TaskPhase(_require_text(row["phase"], "SEM task phase")),
            base_generation=_require_text(row["base_generation"], "SEM task base generation"),
            final_generation=_optional_text(row["final_generation"], "SEM task final generation"),
            terminal_reason=_optional_text(row["terminal_reason"], "SEM task terminal reason"),
        ))
    return tuple(result)


def _decode_telemetry(value: object) -> TelemetrySnapshot:
    data = _require_dict(
        value, "SEM evolution telemetry",
        {"node_stats", "queries", "incidents", "tasks", "block_incident_cursor", "block_query_cursor"},
    )
    raw_stats = _require_dict(data["node_stats"], "SEM telemetry node_stats")
    node_stats = {
        _require_text(node_id, "SEM telemetry node id"): dict(_require_dict(row, "SEM telemetry node stats"))
        for node_id, row in raw_stats.items()
    }
    query_fields = set(QueryObservation.__dataclass_fields__)
    queries: list[QueryObservation] = []
    for item in _require_list(data["queries"], "SEM telemetry queries"):
        row = _require_dict(item, "SEM telemetry query", query_fields)
        queries.append(QueryObservation(
            query_id=_require_text(row["query_id"], "SEM telemetry query id"),
            task_id=_require_text(row["task_id"], "SEM telemetry query task id"),
            intent=_require_text(row["intent"], "SEM telemetry query intent"),
            opportunity_key=_optional_text(row["opportunity_key"], "SEM telemetry opportunity key"),
            selected_nodes=_require_string_array(row["selected_nodes"], "SEM telemetry selected nodes"),
            returned_node_ids=_require_string_array(row["returned_node_ids"], "SEM telemetry returned nodes"),
            returned_record_ids=_require_string_array(row["returned_record_ids"], "SEM telemetry returned record ids"),
            top_score=_require_number(row["top_score"], "SEM telemetry top score"),
            record_count=_require_int(row["record_count"], "SEM telemetry record count"),
            source_ref_count=_require_int(row["source_ref_count"], "SEM telemetry source-ref count"),
        ))
    incident_fields = {"incident_id", "kind", "task_id", "intent", "node_ids", "detail"}
    incidents: list[MemoryIncident] = []
    for item in _require_list(data["incidents"], "SEM telemetry incidents"):
        row = _require_dict(item, "SEM telemetry incident", incident_fields)
        incidents.append(MemoryIncident(
            incident_id=_require_text(row["incident_id"], "SEM incident id"),
            kind=IncidentKind(_require_text(row["kind"], "SEM incident kind")),
            task_id=_require_text(row["task_id"], "SEM incident task id"),
            intent=_require_text(row["intent"], "SEM incident intent"),
            node_ids=_require_string_array(row["node_ids"], "SEM incident node ids"),
            detail=dict(_require_dict(row["detail"], "SEM incident detail")),
        ))
    task_fields = set(TaskObservation.__dataclass_fields__)
    tasks: list[TaskObservation] = []
    for item in _require_list(data["tasks"], "SEM telemetry tasks"):
        row = _require_dict(item, "SEM telemetry task", task_fields)
        tasks.append(TaskObservation(
            task_id=_require_text(row["task_id"], "SEM telemetry task id"),
            family=_require_text(row["family"], "SEM telemetry task family"),
            success=_require_bool(row["success"], "SEM telemetry task success"),
            utility=_require_number(row["utility"], "SEM telemetry task utility"),
            blocked_by_prior_progress=_require_bool(
                row["blocked_by_prior_progress"], "SEM telemetry blocked_by_prior_progress"
            ),
        ))
    return TelemetrySnapshot(
        node_stats=node_stats, queries=tuple(queries), incidents=tuple(incidents), tasks=tuple(tasks),
        block_incident_cursor=_require_int(data["block_incident_cursor"], "SEM incident cursor"),
        block_query_cursor=_require_int(data["block_query_cursor"], "SEM query cursor"),
    )


def _decode_serving_state(value: object) -> ServingRuntimeState:
    data = _require_dict(value, "SEM serving snapshot", {"state_kind", "schema_version", "payload"})
    return ServingRuntimeState(
        _require_text(data["state_kind"], "SEM serving state kind"),
        _require_text(data["schema_version"], "SEM serving schema version"),
        dict(_require_dict(data["payload"], "SEM serving snapshot payload")),
    )


def payload_from_document(data: dict[str, Any]) -> SEMSnapshotPayload:
    expected = {
        "state", "lineage", "task_progress", "pending_observations",
        "evolution_telemetry", "serving_state", "evidence",
    }
    document = _require_dict(data, "SEM snapshot document", expected)
    return SEMSnapshotPayload(
        SEMSessionStateSnapshot(
            _decode_state(document["state"]),
            _decode_evidence(document["evidence"]),
            _decode_lineage(document["lineage"]),
        ),
        _decode_pending(document["pending_observations"]),
        _decode_task_progress(document["task_progress"]),
        _decode_telemetry(document["evolution_telemetry"]),
        _decode_serving_state(document["serving_state"]),
    )
