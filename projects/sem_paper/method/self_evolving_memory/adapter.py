from __future__ import annotations

import base64

from noetrium.contracts import (
    AgentMemoryContext,
    AgentGoal,
    AgentObservation,
    MethodSnapshot,
    RecallRequest,
    canonical_digest,
)
from noetrium.contracts.systems.participant__agent import (
    AgentMemoryCheckpoint,
    AgentMemoryCheckpointRecord,
)

from .core import SEMMethodSession, SEM_METHOD_ID


class SemMethodAgentMemoryAdapter:
    """The only cognition-to-SEM memory seam.

    Minecraft cognition receives the platform memory shape, while all method
    generation, query, and checkpoint identity remains in SEMMethodSession.
    """

    def __init__(self, session: SEMMethodSession) -> None:
        self.session = session

    def recall(
        self,
        goal: AgentGoal,
        observation: AgentObservation,
        context: object,
    ) -> AgentMemoryContext:
        result = self.session.recall(
            RecallRequest(
                intent=f"{goal.objective} {observation.state}",
                context=context,
                limit=8,
            )
        )
        return AgentMemoryContext(
            context_text=result.context_text,
            generation=result.method_generation,
            artifacts=result.artifacts,
            query_id=f"{self.session.session_id}:q{self.session.diagnostics()['memory_queries']}",
        )

    def record(self, receipt: object, context: object) -> None:
        self.session.ingest(
            {"kind": "agent_step_receipt", "receipt": str(receipt)},
            context,
        )

    def checkpoint(self) -> AgentMemoryCheckpoint:
        snapshot = self.session.checkpoint()
        step = int(self.session.diagnostics().get("memory_queries", 0))
        record = AgentMemoryCheckpointRecord(
            memory_id=f"{self.session.session_id}:sem-snapshot",
            plane="method",
            kind="sem_snapshot",
            content=base64.b64encode(snapshot.opaque_payload).decode("ascii"),
            generation=snapshot.payload_sha256,
            state_digest=snapshot.payload_sha256,
            tags=("sem", "method-snapshot"),
            verified=True,
            step=step,
            artifact_refs=(snapshot.payload_sha256,),
        )
        return AgentMemoryCheckpoint(sequence_counter=step, records=(record,))

    def restore(self, checkpoint: AgentMemoryCheckpoint) -> None:
        if not isinstance(checkpoint, AgentMemoryCheckpoint):
            raise TypeError("SEM agent memory checkpoint must use Noetrium's public type")
        records = tuple(
            record for record in checkpoint.records
            if record.kind == "sem_snapshot"
            and record.memory_id == f"{self.session.session_id}:sem-snapshot"
        )
        if len(records) != 1:
            raise ValueError("SEM agent memory checkpoint must contain exactly one matching snapshot")
        record = records[0]
        payload = base64.b64decode(record.content.encode("ascii"), validate=True)
        snapshot = MethodSnapshot(
            SEM_METHOD_ID,
            "3.0.0",
            "1",
            canonical_digest({"session_id": self.session.session_id, "treatment": self.session.treatment_id}),
            self.session.session_id,
            record.state_digest,
            payload,
        )
        self.session.restore(snapshot)

    def diagnostics(self) -> dict[str, object]:
        return dict(self.session.diagnostics())