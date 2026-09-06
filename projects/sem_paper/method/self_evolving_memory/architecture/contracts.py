from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
import heapq
import math
import re
from types import MappingProxyType
from typing import Any


def _require_text(value: object, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        kind = "a string" if allow_empty else "a non-empty string"
        raise ValueError(f"{label} must be {kind}")
    return value


def _require_text_tuple(value: object, label: str, *, unique: bool = False) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{label} must be a tuple")
    result = tuple(_require_text(item, f"{label} entry") for item in value)
    if unique and len(result) != len(set(result)):
        raise ValueError(f"{label} entries must be unique")
    return result


def _freeze_json_value(value: object, label: str) -> object:
    """Snapshot a JSON-shaped identity input into recursively immutable values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{label} numeric values must be finite")
        return value
    if isinstance(value, Mapping):
        snapshot: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{label} object keys must be strings")
            snapshot[key] = _freeze_json_value(item, f"{label}.{key}")
        return MappingProxyType(snapshot)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json_value(item, f"{label} item") for item in value)
    raise ValueError(f"{label} must contain only JSON-compatible values")


def architecture_value_to_json(value: object) -> object:
    """Return a detached JSON-compatible representation of a frozen IR value."""
    if isinstance(value, Mapping):
        return {key: architecture_value_to_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [architecture_value_to_json(item) for item in value]
    return value


class PrimitiveType(StrEnum):
    TEXT = "TEXT"
    CATEGORY = "CATEGORY"
    BOOL = "BOOL"
    INT = "INT"
    FLOAT = "FLOAT"
    ENTITY = "ENTITY"
    POSITION = "POSITION"
    TIME = "TIME"
    ACTION = "ACTION"
    OUTCOME = "OUTCOME"
    EVIDENCE_REF = "EVIDENCE_REF"
    MEMORY_REF = "MEMORY_REF"


class ContainerKind(StrEnum):
    SCALAR = "SCALAR"
    OPTIONAL = "OPTIONAL"
    LIST = "LIST"
    SET = "SET"


class MemoryScope(StrEnum):
    WORLD = "WORLD"
    AGENT = "AGENT"


class MemoryMode(StrEnum):
    APPEND = "APPEND"
    CURRENT = "CURRENT"
    AGGREGATE = "AGGREGATE"


class AccessMode(StrEnum):
    SEMANTIC = "SEMANTIC"
    ENTITY = "ENTITY"
    SPATIAL = "SPATIAL"
    TEMPORAL = "TEMPORAL"
    EXACT = "EXACT"


class OperatorKind(StrEnum):
    FILTER = "FILTER"
    PROJECT = "PROJECT"
    GROUP_BY = "GROUP_BY"
    DEDUP = "DEDUP"
    UNION = "UNION"
    AGGREGATE_STATS = "AGGREGATE_STATS"
    SEMANTIC_MAP = "SEMANTIC_MAP"
    SEMANTIC_REDUCE = "SEMANTIC_REDUCE"
    SEMANTIC_COMPOSE = "SEMANTIC_COMPOSE"


class SourceKind(StrEnum):
    EVIDENCE = "EVIDENCE"
    NODE = "NODE"


class EvidenceSourceChannel(StrEnum):
    MEMORY = "MEMORY"
    AUDIT = "AUDIT"


class PredicateOp(StrEnum):
    EQ = "EQ"
    NE = "NE"
    IN = "IN"
    NOT_IN = "NOT_IN"
    LT = "LT"
    LE = "LE"
    GT = "GT"
    GE = "GE"


@dataclass(frozen=True, slots=True)
class TypeSpec:
    base: PrimitiveType
    container: ContainerKind = ContainerKind.SCALAR

    def __post_init__(self) -> None:
        if not isinstance(self.base, PrimitiveType) or not isinstance(self.container, ContainerKind):
            raise ValueError("memory architecture type spec must use typed enums")

    def canonical(self) -> str:
        if self.container is ContainerKind.SCALAR:
            return self.base.value
        return f"{self.container.value}[{self.base.value}]"


_TYPE_RE = re.compile(r"^(OPTIONAL|LIST|SET)\[([A-Z_]+)\]$")


def parse_type_spec(text: str) -> TypeSpec:
    text = _require_text(text, "memory architecture type expression").strip()
    if text in PrimitiveType._value2member_map_:
        return TypeSpec(PrimitiveType(text))
    match = _TYPE_RE.fullmatch(text)
    if not match:
        raise ValueError(f"unsupported type expression: {text}")
    container, base = match.groups()
    if base not in PrimitiveType._value2member_map_:
        raise ValueError(f"unknown primitive type: {base}")
    return TypeSpec(PrimitiveType(base), ContainerKind(container))


@dataclass(frozen=True, slots=True)
class FieldSpec:
    name: str
    dtype: TypeSpec
    required: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        _require_text(self.name, "memory architecture field name")
        if not isinstance(self.dtype, TypeSpec):
            raise ValueError("memory architecture field dtype must be typed")
        if not isinstance(self.required, bool):
            raise ValueError("memory architecture field required must be boolean")
        _require_text(self.description, "memory architecture field description", allow_empty=True)


@dataclass(frozen=True, slots=True)
class SourceSpec:
    kind: SourceKind
    node_id: str | None = None
    event_types: tuple[str, ...] = ()
    evidence_channel: EvidenceSourceChannel = EvidenceSourceChannel.MEMORY

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SourceKind):
            raise ValueError("memory architecture source kind must be typed")
        if self.node_id is not None:
            _require_text(self.node_id, "memory architecture source node_id")
        _require_text_tuple(self.event_types, "memory architecture source event_types", unique=True)
        if not isinstance(self.evidence_channel, EvidenceSourceChannel):
            raise ValueError("memory architecture evidence channel must be typed")


@dataclass(frozen=True, slots=True)
class PredicateAtom:
    field: str
    op: PredicateOp
    value: Any

    def __post_init__(self) -> None:
        _require_text(self.field, "memory architecture predicate field")
        if not isinstance(self.op, PredicateOp):
            raise ValueError("memory architecture predicate op must be typed")
        object.__setattr__(self, "value", _freeze_json_value(self.value, "memory architecture predicate value"))


@dataclass(frozen=True, slots=True)
class RecordSelector:
    all_of: tuple[PredicateAtom, ...] = ()
    negated: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.all_of, tuple) or any(not isinstance(atom, PredicateAtom) for atom in self.all_of):
            raise ValueError("memory architecture selector atoms must be a typed tuple")
        if not isinstance(self.negated, bool):
            raise ValueError("memory architecture selector negated must be boolean")

    def complement(self) -> "RecordSelector":
        return RecordSelector(self.all_of, not self.negated)


@dataclass(frozen=True, slots=True)
class SemanticObjective:
    text: str

    def __post_init__(self) -> None:
        _require_text(self.text, "memory architecture semantic objective")


@dataclass(frozen=True, slots=True)
class SourceRequirement:
    source_node_id: str
    required_fields: tuple[tuple[str, TypeSpec | None], ...]

    def __post_init__(self) -> None:
        _require_text(self.source_node_id, "memory architecture source requirement node_id")
        if not isinstance(self.required_fields, tuple):
            raise ValueError("memory architecture source requirement fields must be a tuple")
        seen: set[str] = set()
        for row in self.required_fields:
            if not isinstance(row, tuple) or len(row) != 2:
                raise ValueError("memory architecture source requirement rows must be two-item tuples")
            name, dtype = row
            _require_text(name, "memory architecture source requirement field")
            if name in seen:
                raise ValueError("memory architecture source requirement fields must be unique")
            seen.add(name)
            if dtype is not None and not isinstance(dtype, TypeSpec):
                raise ValueError("memory architecture source requirement dtype must be typed when present")


@dataclass(frozen=True, slots=True)
class TransformOpSpec:
    op: OperatorKind
    inputs: tuple[str, ...] = ()
    params: Mapping[str, Any] = field(default_factory=dict)
    objective: SemanticObjective | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.op, OperatorKind):
            raise ValueError("memory architecture transform op must be typed")
        _require_text_tuple(self.inputs, "memory architecture transform inputs", unique=True)
        if not isinstance(self.params, Mapping):
            raise ValueError("memory architecture transform params must be a mapping")
        frozen = _freeze_json_value(self.params, "memory architecture transform params")
        if not isinstance(frozen, Mapping):
            raise ValueError("memory architecture transform params must remain an object")
        object.__setattr__(self, "params", frozen)
        if self.objective is not None and not isinstance(self.objective, SemanticObjective):
            raise ValueError("memory architecture transform objective must be typed when present")


@dataclass(frozen=True, slots=True)
class TransformPlan:
    ops: tuple[TransformOpSpec, ...]
    output_ref: str = "out"
    source_requirements: tuple[SourceRequirement, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.ops, tuple) or any(not isinstance(op, TransformOpSpec) for op in self.ops):
            raise ValueError("memory architecture transform ops must be a typed tuple")
        _require_text(self.output_ref, "memory architecture transform output_ref")
        if not isinstance(self.source_requirements, tuple) or any(
            not isinstance(requirement, SourceRequirement) for requirement in self.source_requirements
        ):
            raise ValueError("memory architecture source requirements must be a typed tuple")
        requirement_ids = tuple(item.source_node_id for item in self.source_requirements)
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError("memory architecture source requirements must use unique source nodes")

    @property
    def semantic_operator_count(self) -> int:
        return sum(op.op.value.startswith("SEMANTIC_") for op in self.ops)


@dataclass(frozen=True, slots=True)
class MemoryNodeSpec:
    node_id: str
    label: str
    purpose: str
    scope: MemoryScope
    mode: MemoryMode
    schema: tuple[FieldSpec, ...]
    primary_key: tuple[str, ...]
    access: frozenset[AccessMode]
    sources: tuple[SourceSpec, ...]
    transform: TransformPlan
    selector: RecordSelector | None = None

    def __post_init__(self) -> None:
        _require_text(self.node_id, "memory architecture node_id")
        _require_text(self.label, "memory architecture node label", allow_empty=True)
        _require_text(self.purpose, "memory architecture node purpose")
        if not isinstance(self.scope, MemoryScope) or not isinstance(self.mode, MemoryMode):
            raise ValueError("memory architecture node scope/mode must be typed")
        if not isinstance(self.schema, tuple) or any(not isinstance(field, FieldSpec) for field in self.schema):
            raise ValueError("memory architecture node schema must be a typed tuple")
        _require_text_tuple(self.primary_key, "memory architecture primary_key", unique=True)
        if not isinstance(self.access, frozenset) or any(not isinstance(mode, AccessMode) for mode in self.access):
            raise ValueError("memory architecture node access must be a typed frozenset")
        if not isinstance(self.sources, tuple) or any(not isinstance(source, SourceSpec) for source in self.sources):
            raise ValueError("memory architecture node sources must be a typed tuple")
        if not isinstance(self.transform, TransformPlan):
            raise ValueError("memory architecture node transform must be typed")
        if self.selector is not None and not isinstance(self.selector, RecordSelector):
            raise ValueError("memory architecture node selector must be typed when present")

    def field_map(self) -> dict[str, FieldSpec]:
        return {field.name: field for field in self.schema}


@dataclass(frozen=True, slots=True)
class MemoryArchitectureSpec:
    format_version: str
    architecture_id: str
    generation: int
    nodes: tuple[MemoryNodeSpec, ...]

    def __post_init__(self) -> None:
        _require_text(self.format_version, "memory architecture format_version")
        _require_text(self.architecture_id, "memory architecture architecture_id")
        if isinstance(self.generation, bool) or not isinstance(self.generation, int) or self.generation < 0:
            raise ValueError("memory architecture generation must be a non-negative integer")
        if not isinstance(self.nodes, tuple) or any(not isinstance(node, MemoryNodeSpec) for node in self.nodes):
            raise ValueError("memory architecture nodes must be a typed tuple")

    def node_map(self) -> dict[str, MemoryNodeSpec]:
        return {node.node_id: node for node in self.nodes}

    def get(self, node_id: str) -> MemoryNodeSpec:
        try:
            return self.node_map()[node_id]
        except KeyError as exc:
            raise KeyError(f"unknown memory architecture node: {node_id}") from exc

    def downstream_ids(self, node_id: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                node.node_id
                for node in self.nodes
                if any(source.kind is SourceKind.NODE and source.node_id == node_id for source in node.sources)
            )
        )

    def topological_order(self) -> tuple[str, ...]:
        nodes = self.node_map()
        indegree = {node_id: 0 for node_id in nodes}
        children: dict[str, list[str]] = {node_id: [] for node_id in nodes}
        for node in self.nodes:
            for source in node.sources:
                if source.kind is SourceKind.NODE and source.node_id in nodes:
                    indegree[node.node_id] += 1
                    children[source.node_id].append(node.node_id)
        ready = [node_id for node_id, degree in indegree.items() if degree == 0]
        heapq.heapify(ready)
        order: list[str] = []
        while ready:
            node_id = heapq.heappop(ready)
            order.append(node_id)
            for child in sorted(children[node_id]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    heapq.heappush(ready, child)
        if len(order) != len(nodes):
            raise ValueError("memory architecture contains a cycle")
        return tuple(order)
