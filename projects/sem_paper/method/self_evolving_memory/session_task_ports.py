from __future__ import annotations

from research_platform.platform.kernel import ExecutionContext

from .session_state_api import SEMSessionStatePort
from .session_snapshot_contracts import SessionMutationRecord


class CellTaskScientificMutationPort:
    """Narrow write adapter used by task coordination; does not expose raw session cell."""

    def __init__(self, cell: SEMSessionStatePort) -> None:
        self._cell = cell

    def commit_task_completed(
        self, context: ExecutionContext
    ) -> tuple[SessionMutationRecord, str]:
        record = self._cell.task_completed(context)
        generation = self._cell.current_generation()
        return record, generation

    def sync_adopted_generation(
        self, generation: str, context: ExecutionContext
    ) -> SessionMutationRecord:
        return self._cell.sync_adopted_generation(generation, context)


__all__ = ["CellTaskScientificMutationPort"]
