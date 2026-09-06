from __future__ import annotations

from research_platform.platform.kernel import ExecutionContext

from .session_state_api import SEMSessionStatePort
from .session_context import SEMSessionContextTracker
from .session_observation import SessionMutationObservationPublisher


class SEMSessionIngestor:
    """Owns the evidence-ingest mutation path and its observation publication."""

    def __init__(
        self,
        cell: SEMSessionStatePort,
        observations: SessionMutationObservationPublisher,
        context: SEMSessionContextTracker,
    ) -> None:
        self._cell = cell
        self._observations = observations
        self._context = context

    def ingest(self, evidence: object, context: ExecutionContext) -> None:
        record = self._cell.ingest(evidence, context)
        self._context.update(context)
        self._observations.emit(record, context)


__all__ = ["SEMSessionIngestor"]
