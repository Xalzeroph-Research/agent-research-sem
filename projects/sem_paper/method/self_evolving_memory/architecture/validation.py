from __future__ import annotations

from dataclasses import dataclass
import re

from .contracts import AccessMode, EvidenceSourceChannel, MemoryArchitectureSpec, MemoryMode, OperatorKind, PrimitiveType, SourceKind


@dataclass(frozen=True, slots=True)
class ArchitectureViolation:
    code: str
    message: str
    path: str = ""


class ArchitectureValidationError(ValueError):
    def __init__(self, violations: tuple[ArchitectureViolation, ...]) -> None:
        self.violations = violations
        summary = "; ".join(f"{item.code}: {item.message}" for item in violations)
        super().__init__(summary or "invalid memory architecture")


@dataclass(frozen=True, slots=True)
class ArchitectureValidationLimits:
    min_nodes: int = 2
    max_nodes: int = 32
    max_fields_per_node: int = 32
    max_sources_per_node: int = 8
    max_primary_key_fields: int = 8
    max_ops_per_node: int = 12
    max_semantic_ops_per_node: int = 4


_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")


class ArchitectureValidator:
    """Current-owner validator for the v034 memory IR invariants.

    It validates structure and data-plane legality only.  It never evaluates
    scientific utility and never reads audit/evaluation evidence.
    """

    def __init__(self, limits: ArchitectureValidationLimits | None = None) -> None:
        self.limits = limits or ArchitectureValidationLimits()

    def report(self, architecture: MemoryArchitectureSpec) -> tuple[ArchitectureViolation, ...]:
        errors: list[ArchitectureViolation] = []
        nodes = architecture.node_map()
        if len(nodes) != len(architecture.nodes):
            errors.append(ArchitectureViolation("ARCH_DUPLICATE_NODE", "duplicate node id"))
        count = len(architecture.nodes)
        if not self.limits.min_nodes <= count <= self.limits.max_nodes:
            errors.append(ArchitectureViolation("ARCH_NODE_LIMIT", f"node count {count} outside configured bounds"))

        for node in architecture.nodes:
            path = f"nodes.{node.node_id}"
            if not node.node_id.strip() or not node.purpose.strip():
                errors.append(ArchitectureViolation("ARCH_NODE_IDENTITY", "node id and purpose are required", path))
            if not 1 <= len(node.schema) <= self.limits.max_fields_per_node:
                errors.append(ArchitectureViolation("ARCH_FIELD_LIMIT", "invalid field count", path))
            if len(node.sources) > self.limits.max_sources_per_node:
                errors.append(ArchitectureViolation("ARCH_SOURCE_LIMIT", "too many sources", path))
            if len(node.primary_key) > self.limits.max_primary_key_fields:
                errors.append(ArchitectureViolation("ARCH_PRIMARY_KEY_LIMIT", "too many primary-key fields", path))
            field_names = [field.name for field in node.schema]
            if len(field_names) != len(set(field_names)):
                errors.append(ArchitectureViolation("ARCH_DUPLICATE_FIELD", "duplicate field name", path))
            for field_name in field_names:
                if not _FIELD_RE.fullmatch(field_name):
                    errors.append(ArchitectureViolation("ARCH_FIELD_NAME", f"invalid field name {field_name}", path))
            for key in node.primary_key:
                if key not in field_names:
                    errors.append(ArchitectureViolation("ARCH_PRIMARY_KEY", f"unknown primary key {key}", path))
            if node.mode is MemoryMode.CURRENT and not node.primary_key:
                errors.append(ArchitectureViolation("ARCH_CURRENT_KEY", "CURRENT requires a primary key", path))
            if node.mode is MemoryMode.APPEND and node.primary_key:
                errors.append(ArchitectureViolation("ARCH_APPEND_KEY", "APPEND forbids a business primary key", path))
            base_types = {field.dtype.base for field in node.schema}
            required_access_types = {
                AccessMode.SPATIAL: PrimitiveType.POSITION,
                AccessMode.ENTITY: PrimitiveType.ENTITY,
                AccessMode.TEMPORAL: PrimitiveType.TIME,
            }
            for access, primitive in required_access_types.items():
                if access in node.access and primitive not in base_types:
                    errors.append(ArchitectureViolation("ARCH_ACCESS_SCHEMA", f"{access.value} requires {primitive.value}", path))
            if len(node.transform.ops) > self.limits.max_ops_per_node:
                errors.append(ArchitectureViolation("ARCH_OPERATOR_LIMIT", "too many transform operators", path))
            if node.transform.semantic_operator_count > self.limits.max_semantic_ops_per_node:
                errors.append(ArchitectureViolation("ARCH_SEMANTIC_LIMIT", "too many semantic operators", path))
            semantic_positions = [
                index
                for index, operation in enumerate(node.transform.ops)
                if operation.op in {OperatorKind.SEMANTIC_MAP, OperatorKind.SEMANTIC_REDUCE, OperatorKind.SEMANTIC_COMPOSE}
            ]
            if semantic_positions and semantic_positions[-1] != len(node.transform.ops) - 1:
                errors.append(ArchitectureViolation("ARCH_SEMANTIC_TERMINAL", "semantic operator must be terminal", path))
            if node.mode is MemoryMode.APPEND:
                allowed = {OperatorKind.FILTER, OperatorKind.PROJECT, OperatorKind.UNION, OperatorKind.SEMANTIC_MAP}
                unsafe = [operation.op.value for operation in node.transform.ops if operation.op not in allowed]
                if unsafe:
                    errors.append(ArchitectureViolation("ARCH_APPEND_TRANSFORM", f"APPEND has non-delta operators: {unsafe}", path))
            for source in node.sources:
                if source.kind is SourceKind.NODE:
                    if source.node_id not in nodes:
                        errors.append(ArchitectureViolation("ARCH_UNKNOWN_SOURCE", f"unknown source {source.node_id}", path))
                    if source.node_id == node.node_id:
                        errors.append(ArchitectureViolation("ARCH_SELF_CYCLE", "node cannot source itself", path))
                elif source.node_id is not None:
                    errors.append(ArchitectureViolation("ARCH_EVIDENCE_SOURCE_ID", "evidence source cannot have node id", path))
                elif source.evidence_channel is not EvidenceSourceChannel.MEMORY:
                    errors.append(ArchitectureViolation("ARCH_CONTROL_SOURCE", "only J_mem may source method nodes", path))
            for requirement in node.transform.source_requirements:
                if requirement.source_node_id not in nodes:
                    errors.append(ArchitectureViolation("ARCH_UNKNOWN_REQUIREMENT_SOURCE", f"unknown source {requirement.source_node_id}", path))
                elif not any(source.kind is SourceKind.NODE and source.node_id == requirement.source_node_id for source in node.sources):
                    errors.append(ArchitectureViolation("ARCH_UNDECLARED_REQUIREMENT_SOURCE", f"{requirement.source_node_id} is not a declared source", path))
                else:
                    provider = nodes[requirement.source_node_id]
                    provider_fields = provider.field_map()
                    for field_name, expected_type in requirement.required_fields:
                        actual = provider_fields.get(field_name)
                        if actual is None:
                            errors.append(ArchitectureViolation("ARCH_SOURCE_FIELD", f"source {requirement.source_node_id} lacks {field_name}", path))
                        elif expected_type is not None and actual.dtype != expected_type:
                            errors.append(ArchitectureViolation("ARCH_SOURCE_TYPE", f"source {requirement.source_node_id}.{field_name} has type {actual.dtype.canonical()}", path))
            if node.selector is not None:
                known_fields = set(node.field_map())
                for atom in node.selector.all_of:
                    if atom.field not in known_fields:
                        errors.append(ArchitectureViolation("ARCH_SELECTOR_FIELD", f"selector references unknown field {atom.field}", path))
        try:
            architecture.topological_order()
        except ValueError:
            errors.append(ArchitectureViolation("ARCH_CYCLE", "architecture contains a cycle"))
        return tuple(errors)

    def verify(self, architecture: MemoryArchitectureSpec) -> None:
        violations = self.report(architecture)
        if violations:
            raise ArchitectureValidationError(violations)
