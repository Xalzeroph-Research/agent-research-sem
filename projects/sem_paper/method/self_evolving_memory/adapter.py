from __future__ import annotations

from noetrium.contracts import (
    AgentMemoryContext,
    AgentGoal,
    AgentObservation,
    RecallRequest,
)

from .core import SEMMethodSession


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

    def diagnostics(self) -> dict[str, object]:
        return dict(self.session.diagnostics())