from __future__ import annotations

from pathlib import Path

from research_platform.governance.architecture.source_scan import SourceInvariantViolation, imports, violation


def audit_sem_snapshot_invariants(root: Path, sem: Path) -> list[SourceInvariantViolation]:
    rows: list[SourceInvariantViolation] = []
    for path in sorted(sem.glob("*.py")):
        if path.name in {"session_persistence.py", "session_snapshot_codec.py"}:
            continue
        for module, line in imports(path):
            if module.rsplit(".", 1)[-1] == "session_snapshot_codec":
                rows.append(violation(
                    root, path, "sem_snapshot_codec_firewall", line,
                    "SEM subsystem imports checkpoint codec outside persistence boundary",
                ))
    return rows


__all__ = ["audit_sem_snapshot_invariants"]
