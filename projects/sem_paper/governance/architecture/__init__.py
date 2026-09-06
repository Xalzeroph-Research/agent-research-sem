from __future__ import annotations

import ast
from pathlib import Path

from research_platform.governance.architecture.source_scan import SourceInvariantViolation, violation

from projects.sem_paper.method.self_evolving_memory.governance.architecture import (
    IMPORT_RULES as SEM_IMPORT_RULES,
    SOURCE_AUTHORITY_RULES as SEM_SOURCE_AUTHORITY_RULES,
    audit_source_invariants as audit_sem_source_invariants,
)


_CONCRETE_LAYER_SEGMENTS = {"runtime", "providers", "composition"}


def _import_targets(tree: ast.AST) -> tuple[tuple[str, int], ...]:
    rows: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            rows.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            rows.append((node.module, node.lineno))
    return tuple(rows)


def _is_concrete_platform_import(module: str) -> bool:
    if not module.startswith("research_platform."):
        return False
    return any(part in _CONCRETE_LAYER_SEGMENTS for part in module.split("."))


def audit_source_invariants(root: Path) -> tuple[SourceInvariantViolation, ...]:
    project = Path(root).resolve() / "projects" / "sem_paper"
    if not project.is_dir():
        return ()
    rows: list[SourceInvariantViolation] = []
    for path in sorted(project.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module, line in _import_targets(tree):
            if _is_concrete_platform_import(module):
                rows.append(
                    violation(
                        root,
                        path,
                        "project_system_api_firewall",
                        line,
                        f"Paper-1 project imports concrete platform layer {module}; projects must depend on system APIs/ports only",
                    )
                )
    return tuple(rows) + tuple(audit_sem_source_invariants(root))


IMPORT_RULES = SEM_IMPORT_RULES
SOURCE_AUTHORITY_RULES = SEM_SOURCE_AUTHORITY_RULES

__all__ = ["IMPORT_RULES", "SOURCE_AUTHORITY_RULES", "audit_source_invariants"]
