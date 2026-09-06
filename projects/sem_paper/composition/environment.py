from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping

from noetrium.contracts import MethodTaskOutcome, RecallRequest, canonical_digest

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


class ScriptedMinecraftEnvironment:
    """Deterministic local environment fixture for protocol/conformance runs.

    It exercises the same MethodSession seam as a real Minecraft provider. It is
    explicitly a smoke fixture and cannot confer claim validity on its output.
    """

    environment_id = "minecraft.scripted.v2"

    def run_suite(
        self,
        *,
        session: SEMMethodSession,
        variant_id: str,
        seed: str,
    ) -> tuple[EnvironmentTaskResult, ...]:
        results = []
        for ordinal, task in enumerate(load_task_manifest()["tasks"]):
            results.append(self._run_task(session, task, variant_id, seed, ordinal))
        return tuple(results)

    def _run_task(
        self,
        session: SEMMethodSession,
        task: Mapping[str, Any],
        variant_id: str,
        seed: str,
        ordinal: int,
    ) -> EnvironmentTaskResult:
        task_id = str(task["task_id"])
        goal = str(task["goal"])
        before = session.recall(RecallRequest(goal, None, limit=4))
        session.ingest(
            {"environment": self.environment_id, "task_id": task_id, "goal": goal},
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