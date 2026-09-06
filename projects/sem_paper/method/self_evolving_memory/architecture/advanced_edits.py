from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

from .edits import MemoryNodeDraft


@dataclass(frozen=True, slots=True)
class RewireSourceEdit:
    operation: Literal["REWIRE_SOURCE"]
    target_node_id: str
    old_source_node_id: str
    new_source_node_id: str


@dataclass(frozen=True, slots=True)
class SubstituteNodeEdit:
    operation: Literal["SUBSTITUTE_NODE"]
    target_node_id: str
    replacement: MemoryNodeDraft


AdvancedArchitectureEdit = Union[RewireSourceEdit, SubstituteNodeEdit]

__all__ = ["AdvancedArchitectureEdit", "RewireSourceEdit", "SubstituteNodeEdit"]
