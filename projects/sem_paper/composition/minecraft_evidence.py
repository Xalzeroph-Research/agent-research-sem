from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
import math
from typing import Any, Mapping, Protocol

from research_platform.environment.minecraft.api import MinecraftJsonValue, MinecraftObservationEvent
from research_platform.participant.method.api import MethodSession
from research_platform.platform.kernel import ExecutionContext, canonical_digest
from research_platform.platform.kernel.errors import describe_exception

from projects.sem_paper.method.self_evolving_memory.evidence_audit import AuditEvidence


class MinecraftEvidenceChannel(StrEnum):
    MEMORY = "MEMORY"
    AUDIT = "AUDIT"


@dataclass(frozen=True, slots=True)
class MinecraftEvidenceCandidate:
    evidence_id: str
    event_type: str
    payload: Mapping[str, MinecraftJsonValue]
    channel: MinecraftEvidenceChannel
    task_id: str | None = None
    context_signature: str = ""


class MinecraftEvidenceAdmissionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"Minecraft evidence admission failed [{code}]: {message}")
        self.code = code


class AuditEvidenceSink(Protocol):
    def append(self, row: AuditEvidence) -> None: ...


class MinecraftObservationView(Protocol):
    """Project-local view; the environment ABI stays behind the composition seam."""

    payload: MinecraftJsonValue


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=repr)


def _position(value: object) -> dict[str, float] | None:
    if not isinstance(value, Mapping) or not all(key in value for key in ("x", "y", "z")):
        return None
    try:
        position = {key: float(value[key]) for key in ("x", "y", "z")}
    except (TypeError, ValueError):
        return None
    return position if all(math.isfinite(value) for value in position.values()) else None


def _observed_at(timestamp_ms: int) -> str:
    return f"unix_ms:{timestamp_ms}"


def _event_id(event: MinecraftObservationEvent, event_type: str, payload: Mapping[str, MinecraftJsonValue]) -> str:
    digest = canonical_digest(
        {
            "source": event.source,
            "sequence": event.sequence,
            "timestamp_ms": event.timestamp_ms,
            "request_id": event.request_id,
            "kind": event.kind,
            "event_type": event_type,
            "payload": dict(payload),
        }
    )
    return "mcev_" + digest[:32]


@dataclass(slots=True)
class MinecraftEvidenceAdapter:
    """Paper-owned MC event normalization; it owns no SEM storage or retrieval."""

    _last_task_id: str | None = None
    _last_task_text: str = ""
    _last_context: str = ""

    def admit(self, event: MinecraftObservationEvent) -> tuple[MinecraftEvidenceCandidate, ...]:
        payload = dict(event.payload)
        if event.kind in {"spawn_snapshot", "self_snapshot"}:
            return (self._self_snapshot(event, payload),)
        if event.kind == "entity_observation":
            candidate = self._entity_observation(event, payload)
            return () if candidate is None else (candidate,)
        if event.kind == "task_event":
            return (self._task_event(event, payload),)
        if event.kind == "action_result":
            return (self._action_result(event, payload),)
        if event.kind in {"health", "death", "bridge_status", "error", "kicked", "end"}:
            return (self._audit_event(event, payload),)
        return ()

    def _candidate(
        self,
        event: MinecraftObservationEvent,
        event_type: str,
        payload: Mapping[str, MinecraftJsonValue],
        channel: MinecraftEvidenceChannel,
    ) -> MinecraftEvidenceCandidate:
        event_id = _event_id(event, event_type, payload)
        normalized = {
            **dict(payload),
            "source_event_id": event_id,
            "event_type": event_type,
            "observed_at": _observed_at(event.timestamp_ms),
            "occurred_at": _observed_at(event.timestamp_ms),
        }
        task_id_value = normalized.get("task_id") or self._last_task_id
        return MinecraftEvidenceCandidate(
            evidence_id=event_id,
            event_type=event_type,
            payload=normalized,
            channel=channel,
            task_id=str(task_id_value) if task_id_value else None,
            context_signature=self._last_context,
        )

    def _self_snapshot(self, event: MinecraftObservationEvent, payload: Mapping[str, MinecraftJsonValue]) -> MinecraftEvidenceCandidate:
        username = str(payload.get("username") or "self")
        state = {
            "health": payload.get("health"),
            "food": payload.get("food"),
            "held_item": payload.get("held_item"),
            "inventory": payload.get("inventory", []),
            "dimension": payload.get("dimension"),
        }
        return self._candidate(
            event,
            "WORLD_OBSERVATION",
            {
                "entity": f"player:{username}",
                "position": _position(payload.get("position")),
                "state_text": _stable_json(state),
                "entity_kind": "PLAYER_SELF",
            },
            MinecraftEvidenceChannel.MEMORY,
        )

    def _entity_observation(
        self,
        event: MinecraftObservationEvent,
        payload: Mapping[str, MinecraftJsonValue],
    ) -> MinecraftEvidenceCandidate | None:
        entity_id = payload.get("uuid") or payload.get("id") or payload.get("username") or payload.get("name")
        if entity_id is None:
            return None
        state = {
            "name": payload.get("name"),
            "username": payload.get("username"),
            "display_name": payload.get("display_name"),
            "type": payload.get("type"),
            "mob_type": payload.get("mob_type"),
            "is_valid": payload.get("is_valid", True),
        }
        return self._candidate(
            event,
            "ENTITY_OBSERVATION",
            {
                "entity": f"entity:{entity_id}",
                "position": _position(payload.get("position")),
                "state_text": _stable_json(state),
                "entity_kind": str(payload.get("mob_type") or payload.get("type") or payload.get("name") or "ENTITY").upper(),
            },
            MinecraftEvidenceChannel.MEMORY,
        )

    def _task_event(self, event: MinecraftObservationEvent, payload: Mapping[str, MinecraftJsonValue]) -> MinecraftEvidenceCandidate:
        task_id = str(payload.get("task_id") or f"task:{event.sequence}")
        task = str(payload.get("task") or payload.get("goal") or "")
        context = str(payload.get("context") or "")
        status = str(payload.get("status") or "OBSERVED").upper()
        self._last_task_id = task_id
        self._last_task_text = task
        self._last_context = context
        return self._candidate(
            event,
            "TASK_EVENT",
            {
                "task": task,
                "context": context,
                "action": "TASK_EVENT",
                "outcome": status,
                "task_lineage": str(payload.get("task_lineage") or task_id),
                "anchors": tuple(str(value) for value in payload.get("anchors", ()) if value is not None),
            },
            MinecraftEvidenceChannel.MEMORY,
        )

    def _action_result(self, event: MinecraftObservationEvent, payload: Mapping[str, MinecraftJsonValue]) -> MinecraftEvidenceCandidate:
        raw_verified = payload.get("verified")
        verified = raw_verified if isinstance(raw_verified, bool) else False
        action_id = payload.get("action_id")
        identity_bound = isinstance(action_id, str) and bool(action_id.strip())
        task = str(payload.get("task") or self._last_task_text)
        context = str(payload.get("context") or self._last_context)
        action = payload.get("action")
        outcome = payload.get("outcome")
        well_formed = isinstance(action, Mapping) and isinstance(outcome, Mapping)
        normalized_action: object = dict(action) if isinstance(action, Mapping) else str(action or "UNKNOWN_ACTION")
        normalized_outcome: object = dict(outcome) if isinstance(outcome, Mapping) else str(outcome or "UNKNOWN_OUTCOME")
        return self._candidate(
            event,
            "ACTION_RESULT",
            {
                "task": task,
                "context": context,
                "action": normalized_action,
                "outcome": normalized_outcome,
                "verified": verified,
                "action_id": action_id if identity_bound else None,
                "task_id": str(payload.get("task_id") or self._last_task_id or ""),
                "task_lineage": str(payload.get("task_lineage") or payload.get("task_id") or self._last_task_id or ""),
                "anchors": tuple(str(value) for value in payload.get("anchors", ()) if value is not None),
            },
            MinecraftEvidenceChannel.MEMORY
            if verified and identity_bound and well_formed
            else MinecraftEvidenceChannel.AUDIT,
        )

    def _audit_event(self, event: MinecraftObservationEvent, payload: Mapping[str, MinecraftJsonValue]) -> MinecraftEvidenceCandidate:
        return self._candidate(
            event,
            "BRIDGE_AUDIT",
            {"bridge_kind": event.kind, "payload": dict(payload)},
            MinecraftEvidenceChannel.AUDIT,
        )


@dataclass(slots=True)
class SEMMinecraftEvidenceIngestor:
    """Routes normalized MC candidates to injected J_mem and J_audit authorities."""

    method: MethodSession
    audit: AuditEvidenceSink
    adapter: MinecraftEvidenceAdapter

    def ingest_event(self, event: MinecraftObservationEvent, context: ExecutionContext) -> tuple[str, ...]:
        if event.kind == "action_result" and context.task_id:
            payload = dict(event.payload)
            task_id = str(payload.get("task_id") or context.task_id)
            if not str(payload.get("task") or "").strip():
                payload["task"] = task_id
            if not str(payload.get("task_id") or "").strip():
                payload["task_id"] = task_id
            if not str(payload.get("task_lineage") or "").strip():
                payload["task_lineage"] = task_id
            event = MinecraftObservationEvent(
                kind=event.kind, payload=payload, sequence=event.sequence,
                timestamp_ms=event.timestamp_ms, source=event.source,
                request_id=event.request_id,
            )
        admitted = self.adapter.admit(event)
        memory_ids: list[str] = []
        for candidate in admitted:
            if candidate.channel is MinecraftEvidenceChannel.MEMORY:
                self.method.ingest(candidate.payload, context)
                memory_ids.append(candidate.evidence_id)
            else:
                self.audit.append(AuditEvidence(candidate.evidence_id, candidate.payload))
        return tuple(memory_ids)

    def ingest_observation(self, observation: MinecraftObservationView, context: ExecutionContext) -> tuple[str, ...]:
        payload = observation.payload
        if not isinstance(payload, Mapping):
            raise MinecraftEvidenceAdmissionError("OBSERVATION_PAYLOAD_INVALID", "MC observation payload must be a mapping")
        events = payload.get("events")
        if not isinstance(events, (list, tuple)):
            raise MinecraftEvidenceAdmissionError("OBSERVATION_EVENTS_INVALID", "MC observation events must be a list")
        memory_ids: list[str] = []
        for row in events:
            if not isinstance(row, Mapping):
                raise MinecraftEvidenceAdmissionError("OBSERVATION_EVENT_INVALID", "MC observation event must be a mapping")
            try:
                event = MinecraftObservationEvent(
                    kind=str(row.get("kind", "")),
                    payload=dict(row.get("payload", {})),
                    sequence=int(row.get("sequence", 0)),
                    timestamp_ms=int(row.get("timestamp_ms", 0)),
                    source=str(row.get("source", "mineflayer")),
                    request_id=None if row.get("request_id") is None else str(row.get("request_id")),
                )
            except (TypeError, ValueError) as exc:
                descriptor = describe_exception(exc)
                raise MinecraftEvidenceAdmissionError(
                    "OBSERVATION_EVENT_INVALID",
                    f"{descriptor.error_type}[{descriptor.error_digest[:16]}]",
                ) from exc
            memory_ids.extend(self.ingest_event(event, context))
        return tuple(memory_ids)


__all__ = [
    "AuditEvidenceSink",
    "MinecraftEvidenceAdapter",
    "MinecraftEvidenceAdmissionError",
    "MinecraftEvidenceCandidate",
    "MinecraftEvidenceChannel",
    "MinecraftObservationView",
    "SEMMinecraftEvidenceIngestor",
]
