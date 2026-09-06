from __future__ import annotations

from enum import StrEnum

from .contracts import (
    AccessMode,
    FieldSpec,
    MemoryArchitectureSpec,
    MemoryMode,
    MemoryNodeSpec,
    MemoryScope,
    OperatorKind,
    PrimitiveType,
    SemanticObjective,
    SourceKind,
    SourceRequirement,
    SourceSpec,
    TransformOpSpec,
    TransformPlan,
    TypeSpec,
    ContainerKind,
)
from .validation import ArchitectureValidator


class SemPaperArchitecturePreset(StrEnum):
    """Research factors owned by the current SEM project."""

    C = "seed_c_v018"
    X = "seed_x_v018"


def _field(name: str, base: PrimitiveType, *, required: bool = True, container: ContainerKind = ContainerKind.SCALAR) -> FieldSpec:
    return FieldSpec(name, TypeSpec(base, container), required)


def _evidence_source(*event_types: str) -> SourceSpec:
    return SourceSpec(SourceKind.EVIDENCE, event_types=tuple(event_types))


def _node_source(node_id: str) -> SourceSpec:
    return SourceSpec(SourceKind.NODE, node_id=node_id)


def _map(objective: str) -> TransformPlan:
    return TransformPlan((TransformOpSpec(OperatorKind.SEMANTIC_MAP, objective=SemanticObjective(objective)),))


def _reduce(node_id: str, objective: str, fields: tuple[str, ...]) -> TransformPlan:
    return TransformPlan(
        (TransformOpSpec(OperatorKind.SEMANTIC_REDUCE, objective=SemanticObjective(objective)),),
        source_requirements=(SourceRequirement(node_id, tuple((name, None) for name in fields)),),
    )


def _seed_c() -> MemoryArchitectureSpec:
    world = MemoryNodeSpec(
        node_id="mem_world",
        label="WorldMemory",
        purpose="Store current grounded entities, locations, and mutable world state relevant to later tasks.",
        scope=MemoryScope.WORLD,
        mode=MemoryMode.CURRENT,
        schema=(
            _field("entity", PrimitiveType.ENTITY),
            _field("position", PrimitiveType.POSITION, required=False, container=ContainerKind.OPTIONAL),
            _field("state_text", PrimitiveType.TEXT),
            _field("entity_kind", PrimitiveType.CATEGORY),
            _field("observed_at", PrimitiveType.TIME),
        ),
        primary_key=("entity",),
        access=frozenset({AccessMode.SEMANTIC, AccessMode.ENTITY, AccessMode.SPATIAL, AccessMode.TEMPORAL, AccessMode.EXACT}),
        sources=(_evidence_source("WORLD_OBSERVATION", "ENTITY_OBSERVATION"),),
        transform=_map("Convert grounded world observations without inventing unobserved facts."),
    )
    experience = MemoryNodeSpec(
        node_id="mem_experience",
        label="ExperienceMemory",
        purpose="Store task-relevant action and outcome episodes from the agent's grounded experience.",
        scope=MemoryScope.AGENT,
        mode=MemoryMode.APPEND,
        schema=(
            _field("task", PrimitiveType.TEXT),
            _field("context", PrimitiveType.TEXT),
            _field("action", PrimitiveType.ACTION),
            _field("outcome", PrimitiveType.OUTCOME),
            _field("occurred_at", PrimitiveType.TIME),
        ),
        primary_key=(),
        access=frozenset({AccessMode.SEMANTIC, AccessMode.TEMPORAL}),
        sources=(_evidence_source("ACTION_RESULT", "TASK_EVENT"),),
        transform=_map("Convert verified action and task evidence into one typed experience record."),
    )
    knowledge = MemoryNodeSpec(
        node_id="mem_knowledge",
        label="KnowledgeMemory",
        purpose="Store reusable regularities supported by accumulated grounded experience.",
        scope=MemoryScope.AGENT,
        mode=MemoryMode.AGGREGATE,
        schema=(_field("subject", PrimitiveType.TEXT), _field("rule", PrimitiveType.TEXT), _field("confidence", PrimitiveType.FLOAT)),
        primary_key=("subject",),
        access=frozenset({AccessMode.SEMANTIC, AccessMode.EXACT}),
        sources=(_node_source("mem_experience"),),
        transform=_reduce(
            "mem_experience",
            "Derive reusable regularities from repeated grounded experience while retaining uncertainty.",
            ("task", "context", "action", "outcome", "occurred_at"),
        ),
    )
    procedure = MemoryNodeSpec(
        node_id="mem_procedure",
        label="ProcedureMemory",
        purpose="Store reusable ordered action patterns supported by successful experience.",
        scope=MemoryScope.AGENT,
        mode=MemoryMode.AGGREGATE,
        schema=(
            _field("goal", PrimitiveType.TEXT),
            _field("steps", PrimitiveType.ACTION, container=ContainerKind.LIST),
            _field("success_rate", PrimitiveType.FLOAT),
        ),
        primary_key=("goal",),
        access=frozenset({AccessMode.SEMANTIC, AccessMode.EXACT}),
        sources=(_node_source("mem_experience"),),
        transform=_reduce(
            "mem_experience",
            "Distill successful repeated action sequences into reusable ordered steps for the same goal class.",
            ("task", "context", "action", "outcome", "occurred_at"),
        ),
    )
    return MemoryArchitectureSpec("sem-paper-architecture-v1", SemPaperArchitecturePreset.C.value, 0, (world, experience, knowledge, procedure))


def _seed_x() -> MemoryArchitectureSpec:
    spatial = MemoryNodeSpec(
        node_id="mem_spatial",
        label="SpatialContext",
        purpose="Maintain current grounded positions of observed world referents for spatial and temporal lookup.",
        scope=MemoryScope.WORLD,
        mode=MemoryMode.CURRENT,
        schema=(
            _field("entity", PrimitiveType.ENTITY),
            _field("position", PrimitiveType.POSITION, required=False, container=ContainerKind.OPTIONAL),
            _field("observed_at", PrimitiveType.TIME),
        ),
        primary_key=("entity",),
        access=frozenset({AccessMode.SEMANTIC, AccessMode.SPATIAL, AccessMode.TEMPORAL, AccessMode.EXACT}),
        sources=(_evidence_source("WORLD_OBSERVATION", "ENTITY_OBSERVATION"),),
        transform=_map("Extract only grounded referent identity, location, and observation time."),
    )
    entity = MemoryNodeSpec(
        node_id="mem_entity",
        label="EntityContext",
        purpose="Maintain current grounded descriptive state of observed world referents.",
        scope=MemoryScope.WORLD,
        mode=MemoryMode.CURRENT,
        schema=(_field("entity", PrimitiveType.ENTITY), _field("state_text", PrimitiveType.TEXT), _field("entity_kind", PrimitiveType.CATEGORY)),
        primary_key=("entity",),
        access=frozenset({AccessMode.SEMANTIC, AccessMode.ENTITY, AccessMode.EXACT}),
        sources=(_evidence_source("WORLD_OBSERVATION", "ENTITY_OBSERVATION"),),
        transform=_map("Extract only grounded referent identity, descriptive state, and kind."),
    )
    event = MemoryNodeSpec(
        node_id="mem_event",
        label="EventHistory",
        purpose="Store task-relevant grounded action and outcome events from the agent's own lifetime.",
        scope=MemoryScope.AGENT,
        mode=MemoryMode.APPEND,
        schema=(_field("task", PrimitiveType.TEXT), _field("context", PrimitiveType.TEXT), _field("action", PrimitiveType.ACTION), _field("outcome", PrimitiveType.OUTCOME), _field("occurred_at", PrimitiveType.TIME)),
        primary_key=(),
        access=frozenset({AccessMode.SEMANTIC, AccessMode.TEMPORAL}),
        sources=(_evidence_source("ACTION_RESULT", "TASK_EVENT"),),
        transform=_map("Convert verified action and task evidence into one typed event-history record."),
    )
    pattern = MemoryNodeSpec(
        node_id="mem_pattern",
        label="PatternMemory",
        purpose="Store reusable regularities and action patterns derived from grounded event history.",
        scope=MemoryScope.AGENT,
        mode=MemoryMode.AGGREGATE,
        schema=(
            _field("pattern_key", PrimitiveType.TEXT),
            _field("pattern_form", PrimitiveType.CATEGORY),
            _field("statement", PrimitiveType.TEXT, required=False, container=ContainerKind.OPTIONAL),
            _field("actions", PrimitiveType.ACTION, required=False, container=ContainerKind.LIST),
            _field("support", PrimitiveType.FLOAT),
        ),
        primary_key=("pattern_key",),
        access=frozenset({AccessMode.SEMANTIC, AccessMode.EXACT}),
        sources=(_node_source("mem_event"),),
        transform=_reduce(
            "mem_event",
            "Derive grounded regularities or ordered action patterns from repeated event history without inventing unsupported fields.",
            ("task", "context", "action", "outcome", "occurred_at"),
        ),
    )
    return MemoryArchitectureSpec("sem-paper-architecture-v1", SemPaperArchitecturePreset.X.value, 0, (spatial, entity, event, pattern))


def build_sem_paper_architecture(preset: SemPaperArchitecturePreset | str = SemPaperArchitecturePreset.C) -> MemoryArchitectureSpec:
    """Return a validated current-project architecture factor.

    The old YAML contracts are migration references only.  The returned
    immutable specification is the current SEM owner and can be serialized,
    fingerprinted, compiled, and projected without importing the old tree.
    """

    selected = SemPaperArchitecturePreset(preset)
    architecture = _seed_c() if selected is SemPaperArchitecturePreset.C else _seed_x()
    ArchitectureValidator().verify(architecture)
    return architecture


__all__ = ["SemPaperArchitecturePreset", "build_sem_paper_architecture"]
