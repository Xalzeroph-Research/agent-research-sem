from __future__ import annotations

import threading
from typing import Any, Callable

from research_platform.platform.kernel import ExecutionContext, JsonValue

from .session_lineage import SessionLineageJournal
from .session_live_state import SessionLiveState
from .session_state_api import PreparedSessionAdoptionPort, SEMSessionClosed
from .session_snapshot_contracts import SEMSessionStateSnapshot, SessionMutationRecord
from .evidence_api import EvidenceReadPort, EvidenceStorePort



class SEMSessionStateCell:
    """Lock/transaction façade over scientific live state and forensic lineage."""

    def __init__(
        self,
        session_id: str,
        live: SessionLiveState,
        lineage: SessionLineageJournal,
        on_mutation: Callable[[SEMSessionStateSnapshot], None] | None = None,
    ) -> None:
        if live.session_id != session_id:
            raise ValueError("SEM session cell/live-state identity mismatch")
        self.session_id = session_id
        self._lock = threading.RLock()
        self._live = live
        self._lineage = lineage
        self._on_mutation = on_mutation

    @classmethod
    def from_snapshot(
        cls,
        session_id: str,
        snapshot: SEMSessionStateSnapshot,
        *,
        limit: int,
        evidence: EvidenceStorePort,
        on_mutation: Callable[[SEMSessionStateSnapshot], None] | None = None,
    ) -> "SEMSessionStateCell":
        live = SessionLiveState.initial(
            session_id,
            evidence,
        )
        live.state = snapshot.state
        lineage = SessionLineageJournal(limit=limit)
        lineage.absorb_snapshot(snapshot.lineage)
        return cls(session_id, live, lineage, on_mutation)

    def _flush(self) -> None:
        if self._on_mutation is not None:
            self._on_mutation(self._snapshot_state_unchecked())

    def _snapshot_state_unchecked(self) -> SEMSessionStateSnapshot:
        return SEMSessionStateSnapshot(
            self._live.state,
            self._live.read_evidence(),
            self._lineage.snapshot(),
        )

    def open_serving_cut(self)->tuple[str,EvidenceReadPort]:
        """Pin generation + append-only evidence view without materializing all payloads."""
        with self._lock:
            self._live.assert_open()
            return (
                self._live.state.architecture_generation,
                self._live.open_evidence_read_view(),
            )

    def current_generation(self)->str:
        """O(1) read of the authoritative session architecture generation."""
        with self._lock:
            self._live.assert_open()
            return self._live.state.architecture_generation

    def evolution_summary(self)->tuple[str,int,str,int,int]:
        """O(1) scientific summary for evolution scheduling/diagnosis adapters."""
        with self._lock:
            self._live.assert_open()
            evidence=self._live.read_evidence_cut()
            state=self._live.state
            return (
                state.architecture_generation,
                state.evidence_sequence,
                evidence.digest,
                state.tasks_completed,
                state.evolution_epoch,
            )

    def ingest(self,payload:JsonValue,context:ExecutionContext|None=None)->SessionMutationRecord:
        with self._lock:
            before=self._live.ingest(payload)
            record = self._lineage.record(
                "INGEST",
                before=before,
                live=self._live,
                context=context,
            )
            self._flush()
            return record

    def task_completed(self,context:ExecutionContext|None=None)->SessionMutationRecord:
        with self._lock:
            before=self._live.task_completed()
            record = self._lineage.record(
                "TASK_COMPLETED",
                before=before,
                live=self._live,
                context=context,
            )
            self._flush()
            return record

    def commit_prepared_adoption(
        self,
        adoption: PreparedSessionAdoptionPort,
        context: ExecutionContext | None = None,
    ) -> tuple[str, SessionMutationRecord]:
        """Commit and publish one adoption under the serving authority lock.

        The injected transaction remains responsible for durable atomic commit.
        Live readers cannot observe the new durable generation before the session
        generation and its forensic lineage have been advanced. If commit raises,
        no session-local state is changed.
        """

        with self._lock:
            self._live.assert_open()
            generation = adoption.commit()
            before = self._live.sync_adopted_generation(generation)
            record = self._lineage.record(
                "ADOPTION_COMMIT",
                before=before,
                live=self._live,
                context=context,
            )
            self._flush()
            return generation, record

    def sync_adopted_generation(self,generation:str,context:ExecutionContext|None=None)->SessionMutationRecord:
        """Synchronize a generation that was committed by the external adoption authority."""
        with self._lock:
            self._live.assert_open()
            if self._live.state.architecture_generation == generation:
                last = self._lineage.last()
                if (
                    last is not None
                    and last.architecture_generation == generation
                    and last.mutation_type in {"ADOPTION_COMMIT", "ADOPTION_SYNC"}
                ):
                    return last
                raise ValueError(
                    "session generation is already current without an adoption publication record"
                )
            before=self._live.sync_adopted_generation(generation)
            record = self._lineage.record(
                "ADOPTION_SYNC",
                before=before,
                live=self._live,
                context=context,
            )
            self._flush()
            return record

    def snapshot_state(self)->SEMSessionStateSnapshot:
        with self._lock:
            self._live.assert_open()
            return self._snapshot_state_unchecked()

    def restore(self,snapshot:SEMSessionStateSnapshot)->SessionMutationRecord:
        with self._lock:
            before=self._live.restore(snapshot)
            self._lineage.absorb_snapshot(snapshot.lineage)
            record = self._lineage.record(
                "RESTORE",
                before=before,
                live=self._live,
                source_revision=snapshot.lineage.revision,
            )
            self._flush()
            return record

    def close(self)->None:
        with self._lock:
            before=self._live.close()
            if before is None:
                return
            self._lineage.record(
                "CLOSE",
                before=before,
                live=self._live,
            )
            self._flush()

    def mutation_history(self,*,limit:int=64)->tuple[SessionMutationRecord,...]:
        with self._lock:
            return self._lineage.history(limit=limit)

    def diagnostics(self)->dict[str,Any]:
        with self._lock:
            self._live.assert_open()
            snapshot=self._live.read_evidence_cut()
            last=self._lineage.last()
            return {
                "revision":self._lineage.revision,
                "generation":self._live.state.architecture_generation,
                "evidence_sequence":self._live.state.evidence_sequence,
                "evidence_digest":snapshot.digest,
                "evolution_epoch":self._live.state.evolution_epoch,
                "tasks_completed":self._live.state.tasks_completed,
                "last_mutation":last.mutation_type if last else None,
                "last_mutation_state_digest":last.after_state_digest if last else None,
                "last_mutation_evidence_digest":last.after_evidence_digest if last else None,
                "mutation_journal_size":len(self._lineage.history(limit=self._lineage.limit)),
            }


__all__=["SEMSessionStateCell","SEMSessionClosed"]
