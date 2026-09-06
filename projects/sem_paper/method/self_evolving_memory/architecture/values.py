from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts import ContainerKind, MemoryNodeSpec, PrimitiveType, TypeSpec


class PayloadValidationError(ValueError):
    pass


def _scalar_ok(base: PrimitiveType, value: Any) -> bool:
    if base in {PrimitiveType.TEXT, PrimitiveType.CATEGORY, PrimitiveType.ENTITY, PrimitiveType.TIME, PrimitiveType.EVIDENCE_REF, PrimitiveType.MEMORY_REF}:
        return isinstance(value, str)
    if base is PrimitiveType.BOOL:
        return isinstance(value, bool)
    if base is PrimitiveType.INT:
        return isinstance(value, int) and not isinstance(value, bool)
    if base is PrimitiveType.FLOAT:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if base is PrimitiveType.POSITION:
        return isinstance(value, Mapping) and all(
            key in value and isinstance(value[key], (int, float)) and not isinstance(value[key], bool)
            for key in ("x", "y", "z")
        )
    if base in {PrimitiveType.ACTION, PrimitiveType.OUTCOME}:
        return isinstance(value, (str, Mapping, list, tuple, bool, int, float)) or value is None
    return False


def validate_type(spec: TypeSpec, value: Any) -> bool:
    if spec.container is ContainerKind.OPTIONAL:
        return value is None or _scalar_ok(spec.base, value)
    if spec.container in {ContainerKind.LIST, ContainerKind.SET}:
        if not isinstance(value, (list, tuple, set)):
            return False
        return all(_scalar_ok(spec.base, item) for item in value)
    return _scalar_ok(spec.base, value)


def validate_payload(node: MemoryNodeSpec, payload: Mapping[str, Any]) -> None:
    fields = node.field_map()
    unknown = set(payload) - set(fields)
    if unknown:
        raise PayloadValidationError(f"unknown fields for {node.node_id}: {sorted(unknown)}")
    for field in node.schema:
        if field.required and field.name not in payload:
            raise PayloadValidationError(f"missing required field {field.name} for {node.node_id}")
        if field.name in payload and not validate_type(field.dtype, payload[field.name]):
            raise PayloadValidationError(f"field {field.name} expected {field.dtype.canonical()} for {node.node_id}")


__all__ = ["PayloadValidationError", "validate_payload", "validate_type"]
