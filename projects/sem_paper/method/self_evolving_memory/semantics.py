from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from noetrium.contracts import canonical_digest


DETERMINISTIC_TRANSFORMS = frozenset({
    "FILTER",
    "PROJECT",
    "GROUP_BY",
    "DEDUP",
    "UNION",
    "AGGREGATE_STATS",
})
SEMANTIC_TRANSFORMS = frozenset({
    "SEMANTIC_MAP",
    "SEMANTIC_REDUCE",
    "SEMANTIC_COMPOSE",
})
_TRANSFORM_ALIASES = {
    "identity": "UNION",
    "state_projection": "PROJECT",
    "episode_append": "UNION",
    "outcome_append": "UNION",
    "semantic_projection": "SEMANTIC_REDUCE",
    "semantic_split": "SEMANTIC_COMPOSE",
    "semantic_merge": "SEMANTIC_COMPOSE",
}


def _json_safe(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, (tuple, list)):
        return all(_json_safe(item) for item in value)
    if isinstance(value, Mapping):
        return all(
            isinstance(key, str) and _json_safe(item)
            for key, item in value.items()
        )
    return False


@dataclass(frozen=True, slots=True)
class TransformSpec:
    kind: str
    version: str = "sem.v1"
    arguments: Mapping[str, Any] = ()

    def __post_init__(self) -> None:
        kind = _TRANSFORM_ALIASES.get(
            str(self.kind).lower(), str(self.kind).upper()
        )
        if kind not in DETERMINISTIC_TRANSFORMS | SEMANTIC_TRANSFORMS:
            raise ValueError(f"unsupported memory transform: {self.kind}")
        if not str(self.version).strip():
            raise ValueError("memory transform version is required")
        if not isinstance(self.arguments, Mapping):
            raise TypeError("memory transform arguments must be a mapping")
        if not _json_safe(self.arguments):
            raise ValueError("memory transform arguments must be JSON-safe")
        forbidden = {"python", "callable", "module", "external_call", "code"}
        if forbidden & {str(key).lower() for key in self.arguments}:
            raise ValueError("memory transform cannot contain executable fields")

    @property
    def canonical_kind(self) -> str:
        return _TRANSFORM_ALIASES.get(str(self.kind).lower(), str(self.kind).upper())

    def as_mapping(self) -> dict[str, Any]:
        return {
            "kind": str(self.kind),
            "operator": self.canonical_kind,
            "version": str(self.version),
            **dict(self.arguments),
        }

    def digest(self) -> str:
        return canonical_digest(self.as_mapping())


def parse_transform(value: Mapping[str, Any]) -> TransformSpec:
    if not isinstance(value, Mapping):
        raise TypeError("memory transform must be a mapping")
    kind = str(value.get("kind", "")).strip()
    if not kind:
        raise ValueError("memory transform kind is required")
    version = str(value.get("version", "sem.v1"))
    reserved = {"kind", "operator", "version"}
    arguments = {
        str(key): item
        for key, item in value.items()
        if key not in reserved
    }
    operator = str(value.get("operator", "")).strip().upper()
    if operator and operator not in DETERMINISTIC_TRANSFORMS | SEMANTIC_TRANSFORMS:
        raise ValueError(f"unsupported memory transform operator: {operator}")
    spec = TransformSpec(kind, version, arguments)
    if operator and operator != spec.canonical_kind:
        raise ValueError("memory transform kind/operator mismatch")
    return spec


def validate_transform(value: Mapping[str, Any]) -> tuple[bool, str]:
    try:
        parse_transform(value)
    except (TypeError, ValueError) as exc:
        return False, str(exc)
    return True, "transform valid"


__all__ = [
    "DETERMINISTIC_TRANSFORMS",
    "SEMANTIC_TRANSFORMS",
    "TransformSpec",
    "parse_transform",
    "validate_transform",
]
