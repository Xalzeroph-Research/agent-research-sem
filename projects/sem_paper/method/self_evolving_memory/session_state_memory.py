from __future__ import annotations

from .evidence_memory import InMemoryEvidenceStore
from .session_cell import SEMSessionStateCell
from .session_lineage import SessionLineageJournal
from .session_live_state import SessionLiveState
from .session_state_api import SEMSessionStatePort


class InMemorySEMSessionStateFactory:
    """Current local SEM session-state backend; all concrete state stores live here."""

    BACKEND_ID = "sem.session_state.memory.v1"
    JOURNAL_LIMIT = 64

    @property
    def backend_id(self) -> str:
        return self.BACKEND_ID

    def create(self, session_id: str) -> SEMSessionStatePort:
        return SEMSessionStateCell(
            session_id,
            SessionLiveState.initial(session_id, InMemoryEvidenceStore()),
            SessionLineageJournal(limit=self.JOURNAL_LIMIT),
        )


__all__ = ["InMemorySEMSessionStateFactory"]
