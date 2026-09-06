from __future__ import annotations

from pathlib import Path

from research_platform.governance.architecture.source_scan import SourceInvariantViolation, imports, method_calls, violation


def audit_sem_authority_invariants(root: Path, sem: Path) -> list[SourceInvariantViolation]:
    rows: list[SourceInvariantViolation] = []
    checks = (
        (sem / "materialization.py", "materialization_jmem_only", ("evidence_audit", "evidence_eval")),
        (sem / "serving.py", "serving_read_only_dependency", ("evolution", "adoption", "evidence_audit", "evidence_eval")),
    )
    for path, invariant, forbidden in checks:
        if not path.exists():
            continue
        for module, line in imports(path):
            if any(token in module for token in forbidden):
                rows.append(violation(root, path, invariant, line, f"forbidden authority dependency {module}"))

    evolution = sem / "evolution"
    for path in sorted(evolution.glob("*.py")) if evolution.exists() else ():
        for module, line in imports(path):
            if any(token in module for token in ("adoption", "session_cell", "session_live_state")):
                rows.append(violation(
                    root, path, "evolution_port_only_authority", line,
                    f"evolution stage imports concrete write authority {module}",
                ))

    session = sem / "session.py"
    if session.exists():
        calls = method_calls(session, "recall")
        if not any(name == "recall" for name, _ in calls):
            rows.append(violation(root, session, "sem_recall_serving_path", 1, "SEMSession.recall does not call a serving boundary"))
        rows.extend(
            violation(root, session, "sem_recall_serving_path", line, "SEMSession.recall bypasses serving through direct state read")
            for name, line in calls
            if name == "read"
        )
    return rows


__all__ = ["audit_sem_authority_invariants"]
