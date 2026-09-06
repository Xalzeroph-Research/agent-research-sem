from __future__ import annotations

from pathlib import Path

from research_platform.governance.architecture.source_scan import SourceInvariantViolation, imports, violation


def audit_sem_evidence_invariants(root: Path, sem: Path) -> list[SourceInvariantViolation]:
    rows: list[SourceInvariantViolation] = []
    for path in sorted(sem.glob("*.py")):
        if path.name == "__init__.py":
            continue
        for module, line in imports(path):
            if module == "evidence" or module.endswith(".evidence"):
                rows.append(violation(
                    root, path, "sem_evidence_physical_firewall", line,
                    "SEM internal imports aggregate evidence module instead of an authority-specific evidence module",
                ))

    backend_cluster = {
        "evidence_memory.py",
        "session_cell.py",
        "session_lineage.py",
        "session_live_state.py",
        "session_state_memory.py",
    }
    backend_leaves = {"evidence_memory", "session_cell", "session_lineage", "session_live_state"}
    for path in sorted(sem.glob("*.py")):
        if path.name in backend_cluster:
            continue
        for module, line in imports(path):
            if module.rsplit(".", 1)[-1] in backend_leaves:
                rows.append(violation(
                    root, path, "sem_state_backend_boundary", line,
                    f"SEM subsystem imports in-memory state-backend implementation {module}; depend on session_state_api/evidence_api",
                ))

    for path in (sem / "evidence_api.py", sem / "evidence_memory.py"):
        if not path.exists():
            continue
        for module, line in imports(path):
            if module.rsplit(".", 1)[-1] in {"retrieval_features", "retrieval_planner"}:
                rows.append(violation(
                    root, path, "sem_evidence_storage_retrieval_firewall", line,
                    f"canonical evidence storage depends on retrieval algorithm {module}",
                ))

    for path in sorted(sem.glob("*.py")):
        if path.name in {"evidence_memory.py", "session_state_memory.py"}:
            continue
        for module, line in imports(path):
            if module.rsplit(".", 1)[-1] == "evidence_memory":
                rows.append(violation(
                    root, path, "sem_evidence_backend_firewall", line,
                    "concrete J_mem backend escaped the session-state backend assembly",
                ))
    return rows


__all__ = ["audit_sem_evidence_invariants"]
