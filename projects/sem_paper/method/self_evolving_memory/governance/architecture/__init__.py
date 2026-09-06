from __future__ import annotations

from pathlib import Path

from research_platform.governance.architecture.import_graph import ImportRule
from research_platform.governance.architecture.source_authority_contracts import SourceAuthorityRule
from research_platform.governance.architecture.source_authority_matchers import suffix_call
from research_platform.governance.architecture.source_scan import SourceInvariantViolation

from .authority import audit_sem_authority_invariants
from .evidence import audit_sem_evidence_invariants
from .evolution import audit_sem_evolution_invariants
from .runtime import audit_sem_runtime_invariants
from .snapshot import audit_sem_snapshot_invariants


def audit_source_invariants(root: Path) -> tuple[SourceInvariantViolation, ...]:
    sem = Path(root).resolve() / "projects" / "sem_paper" / "method" / "self_evolving_memory"
    if not sem.exists():
        return ()
    return tuple(
        audit_sem_evidence_invariants(root, sem)
        + audit_sem_authority_invariants(root, sem)
        + audit_sem_runtime_invariants(root, sem)
        + audit_sem_snapshot_invariants(root, sem)
        + audit_sem_evolution_invariants(root, sem)
    )


IMPORT_RULES: tuple[ImportRule, ...] = (
    ImportRule(
        "projects.sem_paper.method.self_evolving_memory",
        "research_platform.environment.runtime.api",
        "SEM method cannot directly operate an environment",
    ),
    ImportRule(
        "projects.sem_paper.method.self_evolving_memory",
        "research_platform.model.serving",
        "SEM method cannot own model serving",
    ),
)

SOURCE_AUTHORITY_RULES: tuple[SourceAuthorityRule, ...] = (
    SourceAuthorityRule(
        "scientific.atomic_state_commit",
        "commit_batch",
        ("projects.sem_paper.method.self_evolving_memory.adoption_commit",),
        suffix_call("commit_batch"),
    ),
    SourceAuthorityRule(
        "sem.evidence_ingest",
        "_cell.ingest",
        ("projects.sem_paper.method.self_evolving_memory.session_ingest",),
        suffix_call("_cell.ingest"),
    ),
    SourceAuthorityRule(
        "sem.task_state_write",
        "_cell.task_completed",
        ("projects.sem_paper.method.self_evolving_memory.session_task_ports",),
        suffix_call("_cell.task_completed"),
    ),
    SourceAuthorityRule(
        "sem.generation_sync",
        "_cell.sync_adopted_generation",
        ("projects.sem_paper.method.self_evolving_memory.session_task_ports",),
        suffix_call("_cell.sync_adopted_generation"),
    ),
)

__all__ = ["IMPORT_RULES", "SOURCE_AUTHORITY_RULES", "audit_source_invariants"]
