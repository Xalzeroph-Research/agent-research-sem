from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping

from research_platform.platform.kernel import JsonValue, canonical_digest

from .architecture import MemoryNodeSpec
from .architecture.records import NodePartitionedRecord
from .evidence_api import EvidenceRecord
from .typed_builders import TypedSemanticNodeTransformPort


def _payload(source: EvidenceRecord | NodePartitionedRecord) -> Mapping[str, JsonValue]:
    value = source.payload
    if not isinstance(value, Mapping):
        raise ValueError(f"SEM grounded source {source!r} has a non-mapping payload")
    return value


def _source_id(source: EvidenceRecord | NodePartitionedRecord) -> str:
    return source.evidence_id if isinstance(source, EvidenceRecord) else source.record_id


def _sequence(source: EvidenceRecord | NodePartitionedRecord) -> int:
    return source.sequence


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"SEM grounded evidence field must be a non-empty string: {field}")
    return value.strip()


def _string(value: object, *, field: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        requirement = "string" if allow_empty else "non-empty string"
        raise ValueError(f"SEM grounded evidence field must be a {requirement}: {field}")
    return value


def _outcome_success(outcome: Mapping[str, JsonValue]) -> bool:
    for field in ("success", "accepted"):
        value = outcome.get(field)
        if value is not None:
            if not isinstance(value, bool):
                raise ValueError(f"SEM action outcome {field} must be boolean")
            return value
    status = outcome.get("status")
    if status is not None:
        if not isinstance(status, str):
            raise ValueError("SEM action outcome status must be a string")
        normalized = status.strip().lower()
        if normalized == "applied":
            return True
        if normalized in {"partial", "rejected"}:
            return False
        raise ValueError(f"unsupported SEM action outcome status: {status}")
    raise ValueError("SEM action outcome lacks explicit success semantics")


def _record(
    node_id: str,
    source: EvidenceRecord | NodePartitionedRecord,
    payload: Mapping[str, JsonValue],
    *,
    text: str,
    source_refs: tuple[str, ...] | None = None,
    record_suffix: str = "",
) -> NodePartitionedRecord:
    source_id = _source_id(source)
    suffix = record_suffix or source_id
    return NodePartitionedRecord(
        node_id=node_id,
        record_id=f"{node_id}:{suffix}",
        sequence=_sequence(source),
        text=text,
        payload=dict(payload),
        source_refs=source_refs or (source_id,),
    )


class GroundedSemanticTransformer(TypedSemanticNodeTransformPort):
    """Materialize SEM factors from the cross-environment grounded evidence schema.

    This is the project-owned semantic transform for the current experiment.
    It performs only declared map/reduce operations from the selected typed
    architecture.  Every output keeps evidence or upstream-node ancestry;
    there is no empty-record, flat-row, or ungrounded-model fallback.
    """

    def transform(
        self,
        *,
        node: MemoryNodeSpec,
        source_records: tuple[EvidenceRecord | NodePartitionedRecord, ...],
    ) -> Iterable[NodePartitionedRecord]:
        if node.node_id in {"mem_world", "mem_spatial", "mem_entity"}:
            yield from self._world_projection(node.node_id, source_records)
            return
        if node.node_id in {"mem_experience", "mem_event"}:
            yield from self._event_projection(node.node_id, source_records)
            return
        if node.node_id == "mem_knowledge":
            yield from self._knowledge_reduce(source_records)
            return
        if node.node_id == "mem_procedure":
            yield from self._procedure_reduce(source_records)
            return
        if node.node_id == "mem_pattern":
            yield from self._pattern_reduce(source_records)
            return
        raise ValueError(f"no grounded SEM transform is declared for node {node.node_id}")

    @staticmethod
    def _world_projection(
        node_id: str,
        sources: tuple[EvidenceRecord | NodePartitionedRecord, ...],
    ) -> Iterable[NodePartitionedRecord]:
        for source in sources:
            payload = _payload(source)
            entity = _text(payload.get("entity"), field="entity")
            if node_id == "mem_world":
                projected = {
                    "entity": entity,
                    "position": payload.get("position"),
                    "state_text": _text(payload.get("state_text"), field="state_text"),
                    "entity_kind": _text(payload.get("entity_kind"), field="entity_kind"),
                    "observed_at": _text(payload.get("observed_at"), field="observed_at"),
                }
                yield _record(node_id, source, projected, text=projected["state_text"])
            elif node_id == "mem_spatial":
                projected = {
                    "entity": entity,
                    "position": payload.get("position"),
                    "observed_at": _text(payload.get("observed_at"), field="observed_at"),
                }
                yield _record(node_id, source, projected, text=entity)
            else:
                projected = {
                    "entity": entity,
                    "state_text": _text(payload.get("state_text"), field="state_text"),
                    "entity_kind": _text(payload.get("entity_kind"), field="entity_kind"),
                }
                yield _record(node_id, source, projected, text=projected["state_text"])

    @staticmethod
    def _event_projection(
        node_id: str,
        sources: tuple[EvidenceRecord | NodePartitionedRecord, ...],
    ) -> Iterable[NodePartitionedRecord]:
        for source in sources:
            payload = _payload(source)
            event_type = _text(payload.get("event_type"), field="event_type")
            task = _text(payload.get("task"), field="task")
            context = _string(payload.get("context"), field="context", allow_empty=True)
            action = payload.get("action")
            raw_outcome = payload.get("outcome")

            if event_type == "ACTION_RESULT":
                if not isinstance(action, Mapping):
                    raise ValueError("SEM ACTION_RESULT evidence action must be an object")
                if not isinstance(raw_outcome, Mapping):
                    raise ValueError("SEM ACTION_RESULT evidence outcome must be an object")
                verified = payload.get("verified")
                if not isinstance(verified, bool):
                    raise ValueError("SEM ACTION_RESULT evidence verified must be boolean")
                if not verified:
                    raise ValueError("unverified ACTION_RESULT cannot enter SEM method memory")
                nested_verified = raw_outcome.get("verified")
                if nested_verified is not None and (
                    not isinstance(nested_verified, bool) or nested_verified != verified
                ):
                    raise ValueError("SEM ACTION_RESULT nested verified conflicts with evidence authority")
                projected_action: object = dict(action)
                outcome: object = {**dict(raw_outcome), "verified": verified}
            elif event_type == "TASK_EVENT":
                if action != "TASK_EVENT":
                    raise ValueError("SEM TASK_EVENT evidence action must be TASK_EVENT")
                projected_action = "TASK_EVENT"
                outcome = _text(raw_outcome, field="outcome")
            else:
                raise ValueError(f"unsupported SEM grounded event type: {event_type}")

            projected = {
                "task": task,
                "context": context,
                "action": projected_action,
                "outcome": outcome,
                "occurred_at": _text(payload.get("occurred_at"), field="occurred_at"),
            }
            yield _record(node_id, source, projected, text=task)

    @staticmethod
    def _knowledge_reduce(
        sources: tuple[EvidenceRecord | NodePartitionedRecord, ...],
    ) -> Iterable[NodePartitionedRecord]:
        groups: dict[str, list[NodePartitionedRecord]] = defaultdict(list)
        for source in sources:
            if not isinstance(source, NodePartitionedRecord):
                raise ValueError("mem_knowledge requires typed mem_experience sources")
            if source.payload.get("action") == "TASK_EVENT":
                continue
            groups[_text(source.payload.get("task"), field="task")].append(source)
        for task, rows in sorted(groups.items()):
            refs = tuple(row.record_id for row in rows)
            payload = {
                "subject": task,
                "rule": "observed action/outcome sequence",
                "confidence": min(1.0, len(rows) / 3.0),
            }
            source = rows[0]
            yield _record(
                "mem_knowledge",
                source,
                payload,
                text=f"{task}: {payload['rule']}",
                source_refs=refs,
                record_suffix=canonical_digest(refs)[:24],
            )

    @staticmethod
    def _procedure_reduce(
        sources: tuple[EvidenceRecord | NodePartitionedRecord, ...],
    ) -> Iterable[NodePartitionedRecord]:
        groups: dict[str, list[NodePartitionedRecord]] = defaultdict(list)
        for source in sources:
            if not isinstance(source, NodePartitionedRecord):
                raise ValueError("mem_procedure requires typed mem_experience sources")
            if source.payload.get("action") == "TASK_EVENT":
                continue
            groups[_text(source.payload.get("task"), field="task")].append(source)
        for task, rows in sorted(groups.items()):
            refs = tuple(row.record_id for row in rows)
            steps = [row.payload["action"] for row in rows]
            successes: list[bool] = []
            for row in rows:
                outcome = row.payload.get("outcome")
                if not isinstance(outcome, Mapping):
                    raise ValueError("mem_procedure requires object ACTION_RESULT outcomes")
                successes.append(_outcome_success(outcome))
            payload = {
                "goal": task,
                "steps": steps,
                "success_rate": sum(successes) / len(successes),
            }
            yield _record(
                "mem_procedure",
                rows[0],
                payload,
                text=task,
                source_refs=refs,
                record_suffix=canonical_digest(refs)[:24],
            )

    @staticmethod
    def _pattern_reduce(
        sources: tuple[EvidenceRecord | NodePartitionedRecord, ...],
    ) -> Iterable[NodePartitionedRecord]:
        groups: dict[str, list[NodePartitionedRecord]] = defaultdict(list)
        for source in sources:
            if not isinstance(source, NodePartitionedRecord):
                raise ValueError("mem_pattern requires typed mem_event sources")
            if source.payload.get("action") == "TASK_EVENT":
                continue
            groups[_text(source.payload.get("task"), field="task")].append(source)
        for task, rows in sorted(groups.items()):
            refs = tuple(row.record_id for row in rows)
            payload = {
                "pattern_key": task,
                "pattern_form": "action_sequence",
                "statement": f"Observed actions for {task}",
                "actions": [row.payload["action"] for row in rows],
                "support": min(1.0, len(rows) / 3.0),
            }
            yield _record(
                "mem_pattern",
                rows[0],
                payload,
                text=task,
                source_refs=refs,
                record_suffix=canonical_digest(refs)[:24],
            )


__all__ = ["GroundedSemanticTransformer"]
