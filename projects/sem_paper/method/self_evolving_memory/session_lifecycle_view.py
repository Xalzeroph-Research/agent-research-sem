from __future__ import annotations

from typing import Any

from .session_state_api import SEMSessionStatePort
from .session_context import SEMSessionContextTracker
from .session_observation import SessionMutationObservationPublisher
from .session_persistence import SEMSessionPersistence
from .task_coordination import SEMTaskCompletionCoordinator


class SEMSessionLifecycleView:
    """Owns diagnostics, observation flushing, history reads, and session close publication."""

    def __init__(
        self,
        cell: SEMSessionStatePort,
        observations: SessionMutationObservationPublisher,
        tasks: SEMTaskCompletionCoordinator,
        persistence: SEMSessionPersistence,
        context: SEMSessionContextTracker,
    ) -> None:
        self._cell = cell
        self._observations = observations
        self._tasks = tasks
        self._persistence = persistence
        self._context = context

    @property
    def generation(self) -> str:
        return self._cell.current_generation()

    def flush_observations(self) -> tuple[str, ...]:
        return self._observations.flush()

    def mutation_history(self, *, limit: int = 64):
        return self._cell.mutation_history(limit=limit)

    def diagnostics(self) -> dict[str, Any]:
        result = self._cell.diagnostics()
        result["snapshot_schema"] = self._persistence.schema_version
        result["pending_observations"] = self._observations.pending_count()
        result.update(self._tasks.diagnostics())
        return result

    def close(self) -> None:
        before = self._cell.mutation_history(limit=1)
        self._cell.close()
        after = self._cell.mutation_history(limit=1)
        if after and (not before or after[-1].revision != before[-1].revision):
            self._observations.emit(after[-1], self._context.current)


__all__ = ["SEMSessionLifecycleView"]
