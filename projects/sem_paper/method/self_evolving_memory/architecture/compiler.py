from __future__ import annotations

from dataclasses import replace
import hashlib

from .contracts import MemoryArchitectureSpec, MemoryNodeSpec, SourceKind
from .edits import CreateNodeEdit, MergeNodesEdit, RetireNodeEdit, SplitNodeEdit, ArchitectureEdit
from .canonical import architecture_digest
from .validation import ArchitectureValidator


class ArchitectureCompileError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _trusted_id(current: MemoryArchitectureSpec, operation: str, role: str, payload: str) -> str:
    raw = f"{architecture_digest(current)}|{operation}|{role}|{payload}".encode("utf-8")
    return "memn_" + hashlib.sha256(raw).hexdigest()[:12]


def _node_shape_equal(left: MemoryNodeSpec, right: MemoryNodeSpec) -> bool:
    return (
        left.scope == right.scope
        and left.mode == right.mode
        and left.schema == right.schema
        and left.primary_key == right.primary_key
        and left.sources == right.sources
        and left.transform == right.transform
    )


class ArchitectureCompiler:
    """Typed architecture edit compiler migrated from the v034 memory IR."""

    def __init__(self, validator: ArchitectureValidator | None = None) -> None:
        self.validator = validator or ArchitectureValidator()

    def compile_edit(self, current: MemoryArchitectureSpec, edit: ArchitectureEdit) -> MemoryArchitectureSpec:
        self.validator.verify(current)
        nodes = list(current.nodes)
        node_map = current.node_map()
        if isinstance(edit, CreateNodeEdit):
            draft = edit.node
            payload = f"{draft.label}|{draft.purpose}|{draft.scope}|{draft.mode}"
            node_id = _trusted_id(current, edit.operation, "create", payload)
            nodes.append(
                MemoryNodeSpec(
                    node_id,
                    draft.label,
                    draft.purpose,
                    draft.scope,
                    draft.mode,
                    draft.schema,
                    draft.primary_key,
                    draft.access,
                    draft.sources,
                    draft.transform,
                    draft.selector,
                )
            )
        elif isinstance(edit, RetireNodeEdit):
            if edit.target_node_id not in node_map:
                raise ArchitectureCompileError("ARCH_UNKNOWN_NODE", "retire target absent")
            if current.downstream_ids(edit.target_node_id):
                raise ArchitectureCompileError("ARCH_RETIRE_NON_LEAF", "retire is leaf-only")
            if len(nodes) - 1 < self.validator.limits.min_nodes:
                raise ArchitectureCompileError("ARCH_NODE_LIMIT", "retire would violate minimum node count")
            nodes = [node for node in nodes if node.node_id != edit.target_node_id]
        elif isinstance(edit, SplitNodeEdit):
            parent = node_map.get(edit.target_node_id)
            if parent is None:
                raise ArchitectureCompileError("ARCH_UNKNOWN_NODE", "split target absent")
            left_id = _trusted_id(current, edit.operation, "matched", edit.target_node_id + edit.matched_child.purpose)
            right_id = _trusted_id(current, edit.operation, "remainder", edit.target_node_id + edit.remainder_child.purpose)
            left = replace(
                parent,
                node_id=left_id,
                label=edit.matched_child.label,
                purpose=edit.matched_child.purpose,
                access=edit.matched_child.access,
                selector=edit.partition,
            )
            right = replace(
                parent,
                node_id=right_id,
                label=edit.remainder_child.label,
                purpose=edit.remainder_child.purpose,
                access=edit.remainder_child.access,
                selector=edit.partition.complement(),
            )
            rewritten = []
            for node in nodes:
                if node.node_id == parent.node_id:
                    continue
                sources = []
                for source in node.sources:
                    if source.kind is SourceKind.NODE and source.node_id == parent.node_id:
                        sources.extend((replace(source, node_id=left_id), replace(source, node_id=right_id)))
                    else:
                        sources.append(source)
                rewritten.append(replace(node, sources=tuple(sources)))
            nodes = rewritten + [left, right]
        elif isinstance(edit, MergeNodesEdit):
            left = node_map.get(edit.left_node_id)
            right = node_map.get(edit.right_node_id)
            if left is None or right is None:
                raise ArchitectureCompileError("ARCH_UNKNOWN_NODE", "merge target absent")
            if left.selector is None or right.selector is None or left.selector.all_of != right.selector.all_of or left.selector.negated == right.selector.negated:
                raise ArchitectureCompileError("ARCH_MERGE_PARTITION", "merge requires complementary selectors")
            if not _node_shape_equal(left, right):
                raise ArchitectureCompileError("ARCH_MERGE_INCOMPATIBLE", "merge requires structurally compatible siblings")
            merged_id = _trusted_id(current, edit.operation, "merged", left.node_id + right.node_id + edit.merged_purpose)
            merged = replace(left, node_id=merged_id, label=edit.merged_label, purpose=edit.merged_purpose, access=edit.merged_access, selector=None)
            rewritten = []
            for node in nodes:
                if node.node_id in {left.node_id, right.node_id}:
                    continue
                sources = []
                seen = set()
                for source in node.sources:
                    if source.kind is SourceKind.NODE and source.node_id in {left.node_id, right.node_id}:
                        source = replace(source, node_id=merged_id)
                    key = (source.kind, source.node_id, source.event_types, source.evidence_channel)
                    if key not in seen:
                        sources.append(source)
                        seen.add(key)
                rewritten.append(replace(node, sources=tuple(sources)))
            nodes = rewritten + [merged]
        else:
            raise ArchitectureCompileError("ARCH_UNKNOWN_EDIT", "unsupported architecture edit")
        candidate = MemoryArchitectureSpec(current.format_version, current.architecture_id, current.generation + 1, tuple(nodes))
        self.validator.verify(candidate)
        if architecture_digest(candidate) == architecture_digest(current):
            raise ArchitectureCompileError("ARCH_NO_OP", "candidate canonical digest is unchanged")
        return candidate


__all__ = ["ArchitectureCompileError", "ArchitectureCompiler"]
