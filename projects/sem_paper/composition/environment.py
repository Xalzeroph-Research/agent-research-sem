from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping

from noetrium.contracts import (
    ActionRequest,
    ActionResult,
    EnvironmentCapability,
    EnvironmentIdentity,
    EnvironmentProviderCapabilities,
    MethodTaskOutcome,
    Observation,
    RecallRequest,
    canonical_bytes,
    canonical_digest,
)

from projects.sem_paper.experiments.protocol import load_task_manifest
from projects.sem_paper.method.self_evolving_memory import SEMMethodSession


@dataclass(frozen=True, slots=True)
class EnvironmentTaskResult:
    task_id: str
    success: bool
    utility: float
    steps: int
    duration_s: float
    memory_queries: int
    blocked: bool
    evidence_digest: str


class _ScriptedMinecraftSession:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._step = 0
        self._closed = False

    def observe(self, context: object) -> Observation:
        if self._closed:
            raise RuntimeError("environment session is closed")
        return Observation(
            f"{self.session_id}:obs:{self._step}", f"g{self._step}",
            {"session_id": self.session_id, "step": self._step},
        )

    def act(self, request: ActionRequest) -> ActionResult:
        if self._closed:
            raise RuntimeError("environment session is closed")
        self._step += 1
        return ActionResult(
            request.action_id, True, self.observe(request.context), None,
            {"environment": "scripted-minecraft", "action_type": request.action_type},
        )

    def reconcile(self, effect: object, context: object) -> object:
        return effect

    def checkpoint(self) -> bytes:
        return canonical_bytes({"session_id": self.session_id, "step": self._step})

    def restore(self, payload: bytes) -> None:
        import json
        value = json.loads(payload.decode("utf-8"))
        if value["session_id"] != self.session_id:
            raise ValueError("environment snapshot identity mismatch")
        self._step = int(value["step"])

    def close(self) -> None:
        self._closed = True


class ScriptedMinecraftEnvironment:
    """Deterministic local environment fixture for protocol/conformance runs.

    It exercises the same MethodSession seam as a real Minecraft provider. It is
    explicitly a smoke fixture and cannot confer claim validity on its output.
    """

    environment_id = "minecraft.scripted.v2"

    @property
    def identity(self) -> EnvironmentIdentity:
        return EnvironmentIdentity(
            self.environment_id, "2.0.0", "1", "1",
            canonical_digest({"provider": self.environment_id}),
        )

    @property
    def capabilities(self) -> EnvironmentProviderCapabilities:
        return EnvironmentProviderCapabilities.fully_recoverable()

    def open_session(self, *, session_id: str, services: object) -> _ScriptedMinecraftSession:
        return _ScriptedMinecraftSession(session_id)

    def run_suite(
        self,
        *,
        session: SEMMethodSession,
        variant_id: str,
        seed: str,
    ) -> tuple[EnvironmentTaskResult, ...]:
        results = []
        environment_session = self.open_session(
            session_id=f"{variant_id}:{seed}", services=object()
        )
        try:
            for ordinal, task in enumerate(load_task_manifest()["tasks"]):
                results.append(
                    self._run_task(
                        session, environment_session, task, variant_id, seed, ordinal
                    )
                )
            environment_session.checkpoint()
            return tuple(results)
        finally:
            environment_session.close()

    def _run_task(
        self,
        session: SEMMethodSession,
        environment_session: _ScriptedMinecraftSession,
        task: Mapping[str, Any],
        variant_id: str,
        seed: str,
        ordinal: int,
    ) -> EnvironmentTaskResult:
        task_id = str(task["task_id"])
        goal = str(task["goal"])
        before = session.recall(RecallRequest(goal, None, limit=4))
        observation = environment_session.observe(None)
        action = environment_session.act(
            ActionRequest(f"task:{task_id}", "run_task", {"task_id": task_id}, None)
        )
        session.ingest(
            {
                "environment": self.environment_id,
                "task_id": task_id,
                "goal": goal,
                "observation": observation.payload,
                "action_accepted": action.accepted,
            },
            None,
        )
        digest = hashlib.sha256(f"{seed}:{variant_id}:{task_id}".encode()).hexdigest()
        score = int(digest[:8], 16) % 100
        boost = {"fixed": 0, "rule": 12, "self": 20}.get(variant_id.split("-")[0], 0)
        success = score < 58 + boost
        blocked = not success and score % 2 == 0
        steps = 8 + (int(digest[8:12], 16) % 20)
        reason = "blocked prerequisite" if blocked else "timeout while completing task"
        outcome = MethodTaskOutcome(
            task_id=task_id,
            family=str(task["family"]),
            lineage_id=str(task["lineage_id"]),
            success=success,
            utility=(1.0 if success else -0.25) + len(before.artifacts) * 0.01,
            steps=steps,
            failure_reason="" if success else reason,
            memory_queries=1,
        )
        session.task_completed(outcome, None)
        evidence_digest = canonical_digest(
            {"task": task_id, "success": success, "generation": session.generation}
        )
        return EnvironmentTaskResult(
            task_id, success, outcome.utility, steps, steps * 0.5,
            1, blocked, evidence_digest,
        )


__all__ = ["EnvironmentTaskResult", "ScriptedMinecraftEnvironment"]