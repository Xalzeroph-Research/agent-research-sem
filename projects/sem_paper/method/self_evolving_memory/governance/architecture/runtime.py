from __future__ import annotations

import ast
from pathlib import Path

from research_platform.governance.architecture.source_scan import SourceInvariantViolation, imports, violation


def audit_sem_runtime_invariants(root: Path, sem: Path) -> list[SourceInvariantViolation]:
    rows: list[SourceInvariantViolation] = []
    implementation = sem / "implementation.py"
    if implementation.exists():
        forbidden = {
            "projects.sem_paper.method.self_evolving_memory.runtime",
            "projects.sem_paper.method.self_evolving_memory.session",
            "projects.sem_paper.method.self_evolving_memory.session_assembly",
            "projects.sem_paper.method.self_evolving_memory.session_cell",
            "projects.sem_paper.method.self_evolving_memory.session_live_state",
            "projects.sem_paper.method.self_evolving_memory.session_serving",
            "projects.sem_paper.method.self_evolving_memory.session_evolution_runtime",
        }
        forbidden_leaves = {
            "runtime", "session", "session_assembly", "session_cell", "session_live_state",
            "session_serving", "session_evolution_runtime", "session_state_memory",
        }
        for module, line in imports(implementation):
            if module in forbidden or module.rsplit(".", 1)[-1] in forbidden_leaves:
                rows.append(violation(
                    root, implementation, "sem_implementation_runtime_firewall", line,
                    f"SEM implementation imports runtime/session authority {module}",
                ))
        tree = ast.parse(implementation.read_text(encoding="utf-8"), filename=str(implementation))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "open_session":
                rows.append(violation(
                    root, implementation, "sem_implementation_runtime_firewall", node.lineno,
                    "SEM implementation may not own open_session runtime lifecycle authority",
                ))

    scientific_modules = (
        sem / "session_serving_api.py",
        sem / "serving_providers.py",
        sem / "session_evolution_api.py",
    )
    forbidden_leaves = {
        "session_cell", "session_live_state", "session_assembly", "session_serving",
        "session_evolution_runtime", "session_state_memory",
    }
    for path in scientific_modules:
        if not path.exists():
            continue
        for module, line in imports(path):
            if module.rsplit(".", 1)[-1] in forbidden_leaves:
                rows.append(violation(
                    root, path, "sem_scientific_provider_runtime_firewall", line,
                    f"scientific provider contract/composition imports SEM runtime authority {module}",
                ))
    return rows


__all__ = ["audit_sem_runtime_invariants"]
