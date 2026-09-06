from __future__ import annotations

from research_platform.participant.agent.api import (
    AgentEvidencePort,
    AgentGoal,
    AgentMemoryContext,
    AgentMemoryPort,
    AgentObservation,
    AgentPlannerPort,
    AgentPlanningRequest,
    AgentProgressPort,
    AgentStepReceipt,
    AgentSkillSelection,
)
from research_platform.participant.method.api import MethodSession, RecallRequest
from research_platform.platform.kernel import canonical_digest
from research_platform.platform.kernel import ExecutionContext

from .minecraft_workload import (
    MinecraftEnvironmentObservation,
    MinecraftEvidencePort,
    MinecraftPlannerPort,
    MinecraftTaskSpec,
)


class SemPaperCognitionPlannerAdapter(AgentPlannerPort):
    """Adapt the existing Paper planner ABI to the generic cognition ABI."""

    def __init__(self, planner: MinecraftPlannerPort, task: MinecraftTaskSpec) -> None:
        self._planner = planner
        self._task = task

    def plan(self, request: AgentPlanningRequest) -> AgentSkillSelection:
        prior_actions = tuple(
            {
                "action_id": summary.action_id,
                "action_type": summary.action_type,
                "accepted": summary.accepted,
                "verified": summary.verified,
                "payload": dict(summary.payload),
            }
            for summary in request.prior_actions
        )
        decision = self._planner.decide(
            task=self._task,
            context=request.context,
            state=request.observation.state,
            memory_context=request.memory.context_text,
            step=request.step,
            prior_actions=prior_actions,
        )
        if decision.action_type == "finish":
            return AgentSkillSelection("minecraft.finish", dict(decision.payload), completion_claim=True, rationale=decision.rationale)
        return AgentSkillSelection(f"minecraft.{decision.action_type}", dict(decision.payload), rationale=decision.rationale)


class SemMethodAgentMemoryAdapter(AgentMemoryPort):
    """Make the bound SEM method the cognition loop's treatment memory.

    The generic agent memory port is intentionally tiny.  For Paper-1 the
    recall authority must be the exact ``MethodSession`` selected by the
    compiled arm.  Verified Minecraft observations/action events are already
    ingested through ``SemPaperCognitionEvidenceAdapter`` and
    ``SEMMinecraftEvidenceIngestor``; ``record`` therefore remains a no-op to
    avoid duplicating evidence in the method journal.
    """

    def __init__(self, method: MethodSession, *, limit: int = 8) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("SEM cognition recall limit must be a positive integer")
        self._method = method
        self._limit = limit

    def recall(
        self,
        goal: AgentGoal,
        observation: AgentObservation,
        context: ExecutionContext,
    ) -> AgentMemoryContext:
        intent = goal.objective
        if goal.context:
            intent = f"{intent}\nGoal context: {dict(goal.context)!r}"
        result = self._method.recall(
            RecallRequest(intent=intent, context=context, limit=self._limit)
        )
        return AgentMemoryContext(
            context_text=result.context_text,
            generation=result.method_generation,
            artifacts=result.artifacts,
            query_id="sem-method-query:"
            + canonical_digest(
                {
                    "goal": goal.digest,
                    "observation": observation.state_digest,
                    "method_generation": result.method_generation,
                    "artifacts": result.artifacts,
                }
            ),
        )

    def record(self, receipt: AgentStepReceipt, context: ExecutionContext) -> None:
        del receipt, context


class SemPaperCognitionEvidenceAdapter(AgentEvidencePort):
    def __init__(self, evidence: MinecraftEvidencePort) -> None:
        self._evidence = evidence

    def ingest(self, observation, context: ExecutionContext) -> None:
        self._evidence.ingest_observation(
            MinecraftEnvironmentObservation(
                observation.observation_id,
                dict(observation.state),
                (dict(observation.evidence_payload) if observation.evidence_payload else {
                    "state": dict(observation.state), "modality": observation.modality
                }),
            ),
            context,
        )


class SemPaperCognitionProgressAdapter(AgentProgressPort):
    """Explicit checkpoint seam; persistence remains owned by composition."""

    def __init__(self, persist) -> None:
        if not callable(persist):
            raise ValueError("cognition checkpoint persist callback is required")
        self._persist = persist

    def persist(self, checkpoint, context: ExecutionContext) -> None:
        self._persist(checkpoint, context)


__all__ = [
    "SemPaperCognitionEvidenceAdapter",
    "SemMethodAgentMemoryAdapter",
    "SemPaperCognitionPlannerAdapter",
    "SemPaperCognitionProgressAdapter",
]
