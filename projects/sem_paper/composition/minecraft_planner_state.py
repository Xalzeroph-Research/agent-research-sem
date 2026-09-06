from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math

from research_platform.platform.kernel import JsonObject, JsonValue


SCHEMA_VERSION = "sem-paper.minecraft-planner-state.v1"
MAX_NEARBY_ENTITIES = 24
MAX_OUTCOME_ERRORS = 6
MAX_DETAIL_ITEMS = 16
MAX_MAPPING_ITEMS = 32
MAX_TEXT_CHARS = 256
RAW_DIAGNOSTIC_FIELDS = frozenset({"protocol_packets"})


def _bounded_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    if len(value) <= MAX_TEXT_CHARS:
        return value
    return value[:MAX_TEXT_CHARS] + f"…<{len(value) - MAX_TEXT_CHARS} chars omitted>"


def _finite_number(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _bounded_json(value: object, *, depth: int = 0) -> JsonValue:
    if value is None or isinstance(value, bool):
        return value
    number = _finite_number(value)
    if number is not None:
        return number
    if isinstance(value, str):
        return _bounded_text(value)
    if depth >= 4:
        return "<nested value omitted>"
    if isinstance(value, Mapping):
        result: JsonObject = {}
        for index, (raw_key, child) in enumerate(sorted(value.items(), key=lambda item: str(item[0]))):
            if index >= MAX_MAPPING_ITEMS:
                result["_omitted_field_count"] = len(value) - MAX_MAPPING_ITEMS
                break
            key = _bounded_text(str(raw_key)) or ""
            if not key:
                continue
            if key in RAW_DIAGNOSTIC_FIELDS:
                if isinstance(child, Sequence) and not isinstance(child, (str, bytes, bytearray)):
                    result[f"{key}_count"] = len(child)
                continue
            result[key] = _bounded_json(child, depth=depth + 1)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = [_bounded_json(item, depth=depth + 1) for item in value[:MAX_DETAIL_ITEMS]]
        if len(value) > MAX_DETAIL_ITEMS:
            items.append({"_omitted_item_count": len(value) - MAX_DETAIL_ITEMS})
        return items
    return _bounded_text(str(value))


@dataclass(frozen=True, slots=True)
class PlannerOutcomeErrorSummary:
    phase: str | None
    message: str | None
    position: JsonValue
    expected_item: str | None
    association_radius: int | float | None
    drop_candidate_count: int
    spawn_candidate_count: int
    collection_candidate_count: int
    protocol_packet_count: int

    @classmethod
    def from_value(cls, value: object) -> "PlannerOutcomeErrorSummary":
        row = value if isinstance(value, Mapping) else {}
        count = lambda key: len(row.get(key, ())) if isinstance(row.get(key), Sequence) and not isinstance(row.get(key), (str, bytes, bytearray)) else 0
        return cls(
            phase=_bounded_text(row.get("phase")),
            message=_bounded_text(row.get("message")),
            position=_bounded_json(row.get("position")),
            expected_item=_bounded_text(row.get("expected_item")),
            association_radius=_finite_number(row.get("association_radius")),
            drop_candidate_count=count("drop_candidates"),
            spawn_candidate_count=count("spawn_candidates"),
            collection_candidate_count=count("collection_candidates"),
            protocol_packet_count=count("protocol_packets"),
        )

    def as_payload(self) -> JsonObject:
        return {
            "phase": self.phase,
            "message": self.message,
            "position": self.position,
            "expected_item": self.expected_item,
            "association_radius": self.association_radius,
            "drop_candidate_count": self.drop_candidate_count,
            "spawn_candidate_count": self.spawn_candidate_count,
            "collection_candidate_count": self.collection_candidate_count,
            "protocol_packet_count": self.protocol_packet_count,
        }


def _outcome_projection(value: object) -> JsonValue:
    if isinstance(value, str):
        return _bounded_text(value)
    if not isinstance(value, Mapping):
        return None
    payload: JsonObject = {}
    for raw_key, child in sorted(value.items(), key=lambda item: str(item[0])):
        key = str(raw_key)
        if key == "errors":
            continue
        if key in RAW_DIAGNOSTIC_FIELDS:
            continue
        payload[key] = _bounded_json(child)
    errors = value.get("errors")
    if isinstance(errors, Sequence) and not isinstance(errors, (str, bytes, bytearray)):
        rows = [PlannerOutcomeErrorSummary.from_value(row).as_payload() for row in errors[:MAX_OUTCOME_ERRORS]]
        payload["errors"] = rows
        payload["error_count"] = len(errors)
    return payload


@dataclass(frozen=True, slots=True)
class SemPaperMinecraftPlannerStateProjection:
    username: str | None
    position: JsonValue
    health: int | float | None
    food: int | float | None
    dimension: str | None
    inventory: JsonValue
    nearby_entities: tuple[JsonValue, ...]
    anchors: JsonValue
    deaths: int | float | None
    last_action_verified: bool | None
    last_action: JsonValue
    last_outcome: JsonValue
    last_event_sequence: int | float | None

    @classmethod
    def from_state(cls, state: Mapping[str, JsonValue]) -> "SemPaperMinecraftPlannerStateProjection":
        entities = state.get("nearby_entities")
        entity_rows = entities if isinstance(entities, Sequence) and not isinstance(entities, (str, bytes, bytearray)) else ()
        projected_entities = tuple(
            _bounded_json(row) for row in entity_rows[:MAX_NEARBY_ENTITIES]
        )
        verified = state.get("last_action_verified")
        return cls(
            username=_bounded_text(state.get("username")),
            position=_bounded_json(state.get("position")),
            health=_finite_number(state.get("health")),
            food=_finite_number(state.get("food")),
            dimension=_bounded_text(state.get("dimension")),
            inventory=_bounded_json(state.get("inventory", {})),
            nearby_entities=projected_entities,
            anchors=_bounded_json(state.get("anchors", {})),
            deaths=_finite_number(state.get("deaths")),
            last_action_verified=verified if isinstance(verified, bool) else None,
            last_action=_bounded_json(state.get("last_action")),
            last_outcome=_outcome_projection(state.get("last_outcome")),
            last_event_sequence=_finite_number(state.get("last_event_sequence")),
        )

    def as_payload(self) -> JsonObject:
        return {
            "schema_version": SCHEMA_VERSION,
            "username": self.username,
            "position": self.position,
            "health": self.health,
            "food": self.food,
            "dimension": self.dimension,
            "inventory": self.inventory,
            "nearby_entities": list(self.nearby_entities),
            "anchors": self.anchors,
            "deaths": self.deaths,
            "last_action_verified": self.last_action_verified,
            "last_action": self.last_action,
            "last_outcome": self.last_outcome,
            "last_event_sequence": self.last_event_sequence,
        }


__all__ = [
    "SCHEMA_VERSION",
    "SemPaperMinecraftPlannerStateProjection",
]
