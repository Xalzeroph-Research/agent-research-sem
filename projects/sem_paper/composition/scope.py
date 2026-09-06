from __future__ import annotations

from research_platform.scope.api import (
    PLATFORM_SCOPE,
    ScopeIdentity,
    ScopeKind,
    ScopeRegistryPort,
)


def register_sem_paper_scope(scopes: ScopeRegistryPort) -> ScopeIdentity:
    """Register the stable Paper scope hierarchy in an injected registry."""

    workspace = ScopeIdentity(ScopeKind.WORKSPACE, "sem-paper-workspace")
    program = ScopeIdentity(ScopeKind.PROGRAM, "sem-paper-program")
    project = ScopeIdentity(ScopeKind.PROJECT, "sem-paper-1")
    scopes.register(workspace, PLATFORM_SCOPE)
    scopes.register(program, workspace)
    scopes.register(project, program)
    return project


__all__ = ["register_sem_paper_scope"]
