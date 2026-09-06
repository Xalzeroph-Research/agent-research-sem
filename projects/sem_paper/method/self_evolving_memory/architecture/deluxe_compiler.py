from __future__ import annotations

"""Conditional Deluxe topology compiler.

The normal Meta grammar remains the four core structural edits.  These two
operations are available only to an explicitly configured offline topology
diagnostic and are never silently enabled by a runtime tier.
"""

from dataclasses import replace
import hashlib

from .advanced_edits import AdvancedArchitectureEdit, RewireSourceEdit, SubstituteNodeEdit
from .canonical import architecture_digest
from .compiler import ArchitectureCompileError, ArchitectureCompiler
from .contracts import MemoryArchitectureSpec, MemoryNodeSpec, SourceKind, SourceRequirement
from .edits import MemoryNodeDraft
from .validation import ArchitectureValidator


def _trusted_id(current: MemoryArchitectureSpec, operation: str, role: str, payload: str) -> str:
    raw = f"{architecture_digest(current)}|{operation}|{role}|{payload}".encode("utf-8")
    return "memn_" + hashlib.sha256(raw).hexdigest()[:12]


class DeluxeArchitectureCompiler(ArchitectureCompiler):
    """Compile optional topology edits without expanding default authority."""

    def __init__(
        self,
        validator: ArchitectureValidator | None = None,
        *,
        allow_rewire: bool = False,
        allow_substitute: bool = False,
    ) -> None:
        super().__init__(validator)
        self.allow_rewire = allow_rewire
        self.allow_substitute = allow_substitute

    def compile_advanced_edit(
        self,
        current: MemoryArchitectureSpec,
        edit: AdvancedArchitectureEdit,
    ) -> MemoryArchitectureSpec:
        self.validator.verify(current)
        nodes = list(current.nodes)
        node_map = current.node_map()
        if isinstance(edit, RewireSourceEdit):
            if not self.allow_rewire:
                raise ArchitectureCompileError(
                    "ARCH_REWIRE_DISABLED",
                    "REWIRE_SOURCE requires explicit topology-trap enablement",
                )
            target = node_map.get(edit.target_node_id)
            new_source = node_map.get(edit.new_source_node_id)
            if target is None or new_source is None:
                raise ArchitectureCompileError("ARCH_UNKNOWN_SOURCE", "rewire target/source absent")
            if edit.old_source_node_id == edit.new_source_node_id:
                raise ArchitectureCompileError("ARCH_NO_OP", "rewire source unchanged")
            found = False
            sources = []
            for source in target.sources:
                if source.kind is SourceKind.NODE and source.node_id == edit.old_source_node_id:
                    sources.append(replace(source, node_id=edit.new_source_node_id))
                    found = True
                else:
                    sources.append(source)
            if not found:
                raise ArchitectureCompileError(
                    "ARCH_REWIRE_SOURCE_ABSENT",
                    "old source is not declared by target",
                )
            requirements = tuple(
                SourceRequirement(
                    edit.new_source_node_id if req.source_node_id == edit.old_source_node_id else req.source_node_id,
                    req.required_fields,
                )
                for req in target.transform.source_requirements
            )
            replacement = replace(
                target,
                sources=tuple(sources),
                transform=replace(target.transform, source_requirements=requirements),
            )
            nodes = [replacement if node.node_id == target.node_id else node for node in nodes]
        elif isinstance(edit, SubstituteNodeEdit):
            if not self.allow_substitute:
                raise ArchitectureCompileError(
                    "ARCH_SUBSTITUTE_DISABLED",
                    "SUBSTITUTE_NODE requires explicit Deluxe enablement",
                )
            old = node_map.get(edit.target_node_id)
            if old is None:
                raise ArchitectureCompileError("ARCH_UNKNOWN_NODE", "substitute target absent")
            draft: MemoryNodeDraft = edit.replacement
            if (old.scope, old.mode, old.schema, old.primary_key) != (
                draft.scope,
                draft.mode,
                draft.schema,
                draft.primary_key,
            ):
                raise ArchitectureCompileError(
                    "ARCH_SUBSTITUTE_CONTRACT",
                    "replacement must preserve scope/mode/schema/primary_key",
                )
            if not old.access.issubset(draft.access):
                raise ArchitectureCompileError(
                    "ARCH_SUBSTITUTE_CONTRACT",
                    "replacement must preserve old access modes",
                )
            replacement_id = _trusted_id(current, edit.operation, "replacement", old.node_id + draft.purpose)
            replacement = MemoryNodeSpec(
                replacement_id,
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
            rewritten = []
            for node in nodes:
                if node.node_id == old.node_id:
                    continue
                sources = tuple(
                    replace(source, node_id=replacement_id)
                    if source.kind is SourceKind.NODE and source.node_id == old.node_id
                    else source
                    for source in node.sources
                )
                requirements = tuple(
                    SourceRequirement(
                        replacement_id if req.source_node_id == old.node_id else req.source_node_id,
                        req.required_fields,
                    )
                    for req in node.transform.source_requirements
                )
                rewritten.append(
                    replace(
                        node,
                        sources=sources,
                        transform=replace(node.transform, source_requirements=requirements),
                    )
                )
            nodes = rewritten + [replacement]
        else:
            raise ArchitectureCompileError("ARCH_UNKNOWN_EDIT", "unknown Deluxe edit")

        candidate = MemoryArchitectureSpec(
            current.format_version,
            current.architecture_id,
            current.generation + 1,
            tuple(nodes),
        )
        self.validator.verify(candidate)
        if architecture_digest(candidate) == architecture_digest(current):
            raise ArchitectureCompileError("ARCH_NO_OP", "candidate canonical hash unchanged")
        return candidate


__all__ = ["DeluxeArchitectureCompiler"]
