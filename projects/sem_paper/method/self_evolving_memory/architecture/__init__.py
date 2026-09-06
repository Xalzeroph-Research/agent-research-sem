"""Authoritative SEM memory-architecture contracts.

This package is the current-project owner of the memory IR previously kept in
the v034 reference tree.  It describes architecture and read projections; it
does not own evidence, evaluation, adoption, or physical storage.
"""

from .contracts import (
    AccessMode,
    ContainerKind,
    EvidenceSourceChannel,
    FieldSpec,
    MemoryArchitectureSpec,
    MemoryMode,
    MemoryNodeSpec,
    MemoryScope,
    OperatorKind,
    PredicateAtom,
    PredicateOp,
    PrimitiveType,
    RecordSelector,
    SemanticObjective,
    SourceKind,
    SourceRequirement,
    SourceSpec,
    TransformOpSpec,
    TransformPlan,
    TypeSpec,
    parse_type_spec,
)
from .compiler import ArchitectureCompileError, ArchitectureCompiler
from .advanced_edits import AdvancedArchitectureEdit, RewireSourceEdit, SubstituteNodeEdit
from .deluxe_compiler import DeluxeArchitectureCompiler
from .canonical import architecture_digest, canonical_architecture_dict
from .edits import (
    ArchitectureEdit,
    CreateNodeEdit,
    MergeNodesEdit,
    MemoryNodeDraft,
    RetireNodeEdit,
    SplitChildDraft,
    SplitNodeEdit,
)
from .serialization import architecture_from_dict, architecture_to_dict
from .validation import ArchitectureValidationError, ArchitectureValidator
from .records import NodePartitionedRecord
from .values import PayloadValidationError, validate_payload, validate_type
from .presets import SemPaperArchitecturePreset, build_sem_paper_architecture

__all__ = [
    "AccessMode",
    "AdvancedArchitectureEdit",
    "ArchitectureCompileError",
    "ArchitectureCompiler",
    "DeluxeArchitectureCompiler",
    "ArchitectureEdit",
    "ArchitectureValidationError",
    "ArchitectureValidator",
    "SemPaperArchitecturePreset",
    "build_sem_paper_architecture",
    "ContainerKind",
    "CreateNodeEdit",
    "EvidenceSourceChannel",
    "FieldSpec",
    "MemoryArchitectureSpec",
    "MemoryMode",
    "MemoryNodeSpec",
    "MemoryNodeDraft",
    "MemoryScope",
    "NodePartitionedRecord",
    "OperatorKind",
    "PredicateAtom",
    "PredicateOp",
    "PrimitiveType",
    "RecordSelector",
    "RetireNodeEdit",
    "RewireSourceEdit",
    "SemanticObjective",
    "SourceKind",
    "SourceRequirement",
    "SplitChildDraft",
    "SplitNodeEdit",
    "SourceSpec",
    "SubstituteNodeEdit",
    "TransformOpSpec",
    "TransformPlan",
    "TypeSpec",
    "architecture_digest",
    "canonical_architecture_dict",
    "architecture_from_dict",
    "architecture_to_dict",
    "parse_type_spec",
    "PayloadValidationError",
    "validate_payload",
    "validate_type",
]
