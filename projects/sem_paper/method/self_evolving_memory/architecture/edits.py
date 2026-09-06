from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

from .contracts import AccessMode, FieldSpec, MemoryMode, MemoryScope, RecordSelector, SourceSpec, TransformPlan


@dataclass(frozen=True, slots=True)
class MemoryNodeDraft:
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


@dataclass(frozen=True, slots=True)
class CreateNodeEdit:
    operation: Literal["CREATE_NODE"]
    node: MemoryNodeDraft


@dataclass(frozen=True, slots=True)
class RetireNodeEdit:
    operation: Literal["RETIRE_NODE"]
    target_node_id: str


@dataclass(frozen=True, slots=True)
class SplitChildDraft:
    label: str
    purpose: str
    access: frozenset[AccessMode]


@dataclass(frozen=True, slots=True)
class SplitNodeEdit:
    operation: Literal["SPLIT_NODE"]
    target_node_id: str
    partition: RecordSelector
    matched_child: SplitChildDraft
    remainder_child: SplitChildDraft


@dataclass(frozen=True, slots=True)
class MergeNodesEdit:
    operation: Literal["MERGE_NODES"]
    left_node_id: str
    right_node_id: str
    merged_label: str
    merged_purpose: str
    merged_access: frozenset[AccessMode]


ArchitectureEdit = Union[CreateNodeEdit, RetireNodeEdit, SplitNodeEdit, MergeNodesEdit]


__all__ = [
    "ArchitectureEdit",
    "CreateNodeEdit",
    "MergeNodesEdit",
    "MemoryNodeDraft",
    "RetireNodeEdit",
    "SplitChildDraft",
    "SplitNodeEdit",
]
