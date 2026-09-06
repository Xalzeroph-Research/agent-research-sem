from __future__ import annotations

from typing import Any

from .contracts import (
    AccessMode,
    EvidenceSourceChannel,
    FieldSpec,
    MemoryArchitectureSpec,
    MemoryMode,
    MemoryNodeSpec,
    MemoryScope,
    OperatorKind,
    PredicateAtom,
    PredicateOp,
    RecordSelector,
    SemanticObjective,
    SourceKind,
    SourceRequirement,
    SourceSpec,
    TransformOpSpec,
    TransformPlan,
    architecture_value_to_json,
    parse_type_spec,
)


def _require_object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"memory architecture {label} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ValueError(f"memory architecture {label} keys must be strings")
    return value


def _require_exact_fields(value: dict[str, Any], label: str, *, required: set[str], optional: set[str] | None = None) -> None:
    optional = optional or set()
    fields = set(value)
    if not required <= fields or fields - required - optional:
        missing = sorted(required - fields)
        unknown = sorted(fields - required - optional)
        raise ValueError(f"memory architecture {label} schema mismatch: missing={missing!r} unknown={unknown!r}")


def _require_array(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"memory architecture {label} must be an array")
    return value


def _require_text(value: object, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        kind = "a string" if allow_empty else "a non-empty string"
        raise ValueError(f"memory architecture {label} must be {kind}")
    return value


def _require_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"memory architecture {label} must be boolean")
    return value


def _require_nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"memory architecture {label} must be a non-negative integer")
    return value


def _require_string_array(value: object, label: str, *, unique: bool = False) -> tuple[str, ...]:
    result = tuple(_require_text(item, f"{label} entry") for item in _require_array(value, label))
    if unique and len(result) != len(set(result)):
        raise ValueError(f"memory architecture {label} entries must be unique")
    return result


def _selector_from_dict(data: object) -> RecordSelector | None:
    if data is None:
        return None
    document = _require_object(data, "selector")
    _require_exact_fields(document, "selector", required={"all_of", "negated"})
    atoms: list[PredicateAtom] = []
    for raw_value in _require_array(document["all_of"], "selector all_of"):
        raw = _require_object(raw_value, "selector atom")
        _require_exact_fields(raw, "selector atom", required={"field", "op", "value"})
        field = _require_text(raw["field"], "selector atom field")
        op = PredicateOp(_require_text(raw["op"], "selector atom op"))
        atoms.append(PredicateAtom(field, op, raw["value"]))
    return RecordSelector(tuple(atoms), _require_bool(document["negated"], "selector negated"))


def _transform_from_dict(data: object) -> TransformPlan:
    document = _require_object(data, "transform")
    _require_exact_fields(document, "transform", required={"ops"}, optional={"output_ref", "source_requirements"})
    requirements: list[SourceRequirement] = []
    for raw_value in _require_array(document.get("source_requirements", []), "transform source_requirements"):
        raw = _require_object(raw_value, "source requirement")
        _require_exact_fields(raw, "source requirement", required={"source_node_id", "fields"})
        fields: list[tuple[str, object | None]] = []
        for item_value in _require_array(raw["fields"], "source requirement fields"):
            item = _require_object(item_value, "source requirement field")
            _require_exact_fields(item, "source requirement field", required={"name"}, optional={"type"})
            name = _require_text(item["name"], "source requirement field name")
            type_spec = None
            if "type" in item:
                type_spec = parse_type_spec(_require_text(item["type"], "source requirement field type"))
            fields.append((name, type_spec))
        requirements.append(SourceRequirement(_require_text(raw["source_node_id"], "source requirement node id"), tuple(fields)))
    operations: list[TransformOpSpec] = []
    for raw_value in _require_array(document["ops"], "transform ops"):
        raw = _require_object(raw_value, "transform op")
        if "op" not in raw:
            raise ValueError("memory architecture transform op requires op")
        op = OperatorKind(_require_text(raw["op"], "transform op kind"))
        inputs = _require_string_array(raw.get("inputs", []), "transform op inputs")
        objective = None
        if "objective" in raw:
            objective = SemanticObjective(_require_text(raw["objective"], "transform op objective").strip())
        params = {key: value for key, value in raw.items() if key not in {"op", "inputs", "objective"}}
        operations.append(TransformOpSpec(op, inputs, params, objective))
    output_ref = _require_text(document.get("output_ref", "out"), "transform output_ref")
    return TransformPlan(tuple(operations), output_ref, tuple(requirements))


def architecture_from_dict(data: dict[str, Any]) -> MemoryArchitectureSpec:
    document = _require_object(data, "document")
    _require_exact_fields(document, "document", required={"format_version", "architecture_id", "generation", "nodes"})
    nodes: list[MemoryNodeSpec] = []
    for raw_value in _require_array(document["nodes"], "nodes"):
        raw = _require_object(raw_value, "node")
        _require_exact_fields(
            raw,
            "node",
            required={"node_id", "label", "purpose", "scope", "mode", "schema", "primary_key", "access", "sources", "transform"},
            optional={"selector"},
        )
        fields: list[FieldSpec] = []
        for field_value in _require_array(raw["schema"], "node schema"):
            field = _require_object(field_value, "field")
            _require_exact_fields(field, "field", required={"name", "type", "required"}, optional={"description"})
            fields.append(
                FieldSpec(
                    _require_text(field["name"], "field name"),
                    parse_type_spec(_require_text(field["type"], "field type")),
                    _require_bool(field["required"], "field required"),
                    _require_text(field.get("description", ""), "field description", allow_empty=True),
                )
            )
        sources: list[SourceSpec] = []
        for source_value in _require_array(raw["sources"], "node sources"):
            source = _require_object(source_value, "source")
            _require_exact_fields(source, "source", required={"kind"}, optional={"node_id", "event_types", "channel"})
            node_id = None if "node_id" not in source else _require_text(source["node_id"], "source node_id")
            event_types = _require_string_array(source.get("event_types", []), "source event_types")
            channel = EvidenceSourceChannel(_require_text(source.get("channel", "MEMORY"), "source channel"))
            sources.append(SourceSpec(SourceKind(_require_text(source["kind"], "source kind")), node_id, event_types, channel))
        nodes.append(
            MemoryNodeSpec(
                node_id=_require_text(raw["node_id"], "node_id"),
                label=_require_text(raw["label"], "node label", allow_empty=True),
                purpose=_require_text(raw["purpose"], "node purpose").strip(),
                scope=MemoryScope(_require_text(raw["scope"], "node scope")),
                mode=MemoryMode(_require_text(raw["mode"], "node mode")),
                schema=tuple(fields),
                primary_key=_require_string_array(raw["primary_key"], "node primary_key"),
                access=frozenset(AccessMode(value) for value in _require_string_array(raw["access"], "node access", unique=True)),
                sources=tuple(sources),
                transform=_transform_from_dict(raw["transform"]),
                selector=_selector_from_dict(raw.get("selector")),
            )
        )
    return MemoryArchitectureSpec(
        _require_text(document["format_version"], "format_version"),
        _require_text(document["architecture_id"], "architecture_id"),
        _require_nonnegative_int(document["generation"], "generation"),
        tuple(nodes),
    )

def architecture_to_dict(architecture: MemoryArchitectureSpec) -> dict[str, Any]:
    def selector_to_dict(selector: RecordSelector | None) -> dict[str, Any] | None:
        if selector is None:
            return None
        return {
            "all_of": [
                {"field": atom.field, "op": atom.op.value, "value": architecture_value_to_json(atom.value)}
                for atom in selector.all_of
            ],
            "negated": selector.negated,
        }

    def transform_to_dict(plan: TransformPlan) -> dict[str, Any]:
        value: dict[str, Any] = {"ops": []}
        for operation in plan.ops:
            thawed_params = architecture_value_to_json(operation.params)
            if not isinstance(thawed_params, dict):
                raise ValueError("memory architecture transform params must materialize as an object")
            item: dict[str, Any] = {"op": operation.op.value, **thawed_params}
            if operation.inputs:
                item["inputs"] = list(operation.inputs)
            if operation.objective is not None:
                item["objective"] = operation.objective.text
            value["ops"].append(item)
        if plan.output_ref != "out":
            value["output_ref"] = plan.output_ref
        if plan.source_requirements:
            value["source_requirements"] = [
                {
                    "source_node_id": requirement.source_node_id,
                    "fields": [
                        {"name": name, **({"type": spec.canonical()} if spec is not None else {})}
                        for name, spec in requirement.required_fields
                    ],
                }
                for requirement in plan.source_requirements
            ]
        return value

    return {
        "format_version": architecture.format_version,
        "architecture_id": architecture.architecture_id,
        "generation": architecture.generation,
        "nodes": [
            {
                "node_id": node.node_id,
                "label": node.label,
                "purpose": node.purpose,
                "scope": node.scope.value,
                "mode": node.mode.value,
                "schema": [
                    {
                        "name": field.name,
                        "type": field.dtype.canonical(),
                        "required": field.required,
                        **({"description": field.description} if field.description else {}),
                    }
                    for field in node.schema
                ],
                "primary_key": list(node.primary_key),
                "access": sorted(access.value for access in node.access),
                "sources": [
                    {
                        "kind": source.kind.value,
                        **({"node_id": source.node_id} if source.node_id else {}),
                        **({"event_types": list(source.event_types)} if source.event_types else {}),
                        **({"channel": source.evidence_channel.value} if source.evidence_channel is not EvidenceSourceChannel.MEMORY else {}),
                    }
                    for source in node.sources
                ],
                "transform": transform_to_dict(node.transform),
                **({"selector": selector_to_dict(node.selector)} if node.selector is not None else {}),
            }
            for node in architecture.nodes
        ],
    }


__all__ = ["architecture_from_dict", "architecture_to_dict"]
