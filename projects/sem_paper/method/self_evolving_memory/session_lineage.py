from __future__ import annotations

from dataclasses import dataclass

from research_platform.platform.kernel import ExecutionContext

from .session_live_state import LiveStateCut, SessionLiveState
from .session_snapshot_contracts import SessionLineageSnapshot, SessionMutationRecord


class SessionLineageJournal:
    """Owns monotonic session revision and bounded forensic mutation lineage only."""

    def __init__(self,*,limit:int)->None:
        if limit<=0:
            raise ValueError("session lineage limit must be positive")
        self.limit=limit
        self._revision=0
        self._tail:list[SessionMutationRecord]=[]

    @property
    def revision(self)->int:
        return self._revision

    @staticmethod
    def _context_fields(context:ExecutionContext|None)->dict[str,str|None]:
        if context is None:
            return {
                "run_id":None,
                "task_id":None,
                "decision_cycle_id":None,
                "operation_id":None,
                "trace_id":None,
                "span_id":None,
            }
        return {
            "run_id":context.run_id,
            "task_id":context.task_id,
            "decision_cycle_id":context.decision_cycle_id,
            "operation_id":context.operation_id,
            "trace_id":context.trace_id,
            "span_id":context.span_id,
        }

    def absorb_snapshot(self,lineage:SessionLineageSnapshot)->None:
        local_revision=self._revision
        if local_revision<=lineage.revision:
            self._tail=list(lineage.mutation_tail[-self.limit:])
        self._revision=max(local_revision,lineage.revision)

    def record(
        self,
        mutation_type:str,
        *,
        before:LiveStateCut,
        live:SessionLiveState,
        context:ExecutionContext|None=None,
        source_revision:int|None=None,
    )->SessionMutationRecord:
        self._revision+=1
        evidence=live.read_evidence_cut()
        record=SessionMutationRecord(
            revision=self._revision,
            mutation_type=mutation_type,
            before_state_digest=before.state_digest,
            after_state_digest=live.state_digest(live.state),
            before_evidence_digest=before.evidence_digest,
            after_evidence_digest=evidence.digest,
            before_closed=before.closed,
            after_closed=live.closed,
            evidence_sequence=live.state.evidence_sequence,
            architecture_generation=live.state.architecture_generation,
            source_revision=source_revision,
            **self._context_fields(context),
        )
        self._tail.append(record)
        if len(self._tail)>self.limit:
            del self._tail[:-self.limit]
        return record

    def snapshot(self)->SessionLineageSnapshot:
        return SessionLineageSnapshot(
            revision=self._revision,
            mutation_tail=tuple(self._tail),
        )

    def history(self,*,limit:int)->tuple[SessionMutationRecord,...]:
        if limit<=0:
            return ()
        return tuple(self._tail[-min(limit,self.limit):])

    def last(self)->SessionMutationRecord|None:
        return self._tail[-1] if self._tail else None
