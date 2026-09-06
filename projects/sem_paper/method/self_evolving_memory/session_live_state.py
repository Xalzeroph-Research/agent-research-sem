from __future__ import annotations

from dataclasses import asdict, dataclass

from research_platform.platform.kernel import JsonValue, canonical_digest, canonical_text
from .evidence_api import EvidenceCut, EvidenceReadPort, EvidenceSnapshot, EvidenceStorePort
from .session_reducer import SEMSessionState, after_adoption, after_ingest, after_task_completed, initial_session_state
from .session_snapshot_contracts import SEMSessionStateSnapshot
from .session_state_api import SEMSessionClosed


@dataclass(frozen=True, slots=True)
class LiveStateCut:
    state_digest: str
    evidence_digest: str
    closed: bool


@dataclass(slots=True)
class SessionLiveState:
    """Single scientific live-state aggregate: state + canonical evidence + closed flag."""

    session_id: str
    state: SEMSessionState
    evidence: EvidenceStorePort
    closed: bool = False

    @classmethod
    def initial(cls, session_id: str, evidence: EvidenceStorePort) -> "SessionLiveState":
        return cls(session_id, initial_session_state(), evidence, False)

    @staticmethod
    def state_digest(state:SEMSessionState)->str:
        return canonical_digest(asdict(state))

    def assert_open(self)->None:
        if self.closed:
            raise SEMSessionClosed("SEM session is closed")

    def cut(self)->LiveStateCut:
        return LiveStateCut(
            self.state_digest(self.state),
            self.evidence.cut().digest,
            self.closed,
        )

    def read_evidence(self)->EvidenceSnapshot:
        return self.evidence.snapshot()

    def read_evidence_cut(self)->EvidenceCut:
        return self.evidence.cut()

    def open_evidence_read_view(self)->EvidenceReadPort:
        return self.evidence.read_view()

    def ingest(self,payload:JsonValue)->LiveStateCut:
        self.assert_open()
        before=self.cut()
        sequence=self.state.evidence_sequence+1
        next_state=after_ingest(
            self.state,
            sequence=sequence,
            grounded_payload=canonical_text(payload),
        )
        self.evidence.append_payload(f"{self.session_id}:jmem:{sequence}",sequence,payload)
        self.state=next_state
        return before

    def task_completed(self)->LiveStateCut:
        self.assert_open()
        before=self.cut()
        self.state=after_task_completed(self.state)
        return before

    def sync_adopted_generation(self,generation:str)->LiveStateCut:
        """Mirror an already-authoritative adoption into session-local scientific state."""
        self.assert_open()
        before=self.cut()
        self.state=after_adoption(self.state,generation=generation)
        return before

    def restore(self,snapshot:SEMSessionStateSnapshot)->LiveStateCut:
        if snapshot.state.evidence_sequence!=snapshot.evidence.sequence:
            raise ValueError("SEM snapshot state/evidence sequence mismatch")
        self.assert_open()
        before=self.cut()
        self.evidence.restore(snapshot.evidence)
        self.state=snapshot.state
        return before

    def close(self)->LiveStateCut|None:
        if self.closed:
            return None
        before=self.cut()
        self.closed=True
        return before
