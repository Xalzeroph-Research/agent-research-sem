from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import time
from uuid import uuid4
from typing import Any, Mapping

from noetrium.contracts import (
    ActionRequest,
    ActionResult,
    AgentGoal,
    AgentMemoryPort,
    AgentObservation,
    AgentStepReceipt,
    EnvironmentCapability,
    EnvironmentIdentity,
    EnvironmentProviderCapabilities,
    EnvironmentSession,
    MethodTaskOutcome,
    ModelProviderProfile,
    Observation,
    RecallRequest,
    canonical_bytes,
    canonical_digest,
)

from noetrium.contracts.systems.model__request import ExecutionContext

from noetrium.platform import (
    bind_bundled_minecraft_environment,
    bind_qualified_project_model,
    run_local_shell_command,
)

from projects.sem_paper.experiments.protocol import PAPER_METHOD_BASE, load_task_manifest
from projects.sem_paper.method.self_evolving_memory import SEMMethodSession
from projects.sem_paper.composition.model_planner import (
    ModelActionPlanner,
    planner_model_requirement,
)


def load_scripted_action_plan(
    task: Mapping[str, Any],
) -> tuple[tuple[str, Mapping[str, Any], float], ...]:
    # Parse an externally supplied fixture plan in the environment adapter.
    # SEM only receives verified outcomes; action vocabulary stays outside it.
    rows = task.get("action_plan", ())
    if not isinstance(rows, (tuple, list)):
        return ()
    plan: list[tuple[str, Mapping[str, Any], float]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        action_type = str(row.get("action_type", "")).strip()
        if not action_type:
            continue
        arguments = row.get("arguments", {})
        if not isinstance(arguments, Mapping):
            continue
        plan.append((
            action_type,
            dict(arguments),
            float(row.get("timeout_s", 90.0)),
        ))
    return tuple(plan)


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
    failure_class: str = ""
    verified_actions: int = 0
    evidence_closed: bool = False
    outcome_codes: tuple[str, ...] = ()
    family: str = ""


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

    def __init__(self) -> None:
        self.last_checkpoint: bytes | None = None

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
        assignment: object | None = None,
        assignment_isolation: object | None = None,
        memory: AgentMemoryPort | None = None,
    ) -> tuple[EnvironmentTaskResult, ...]:
        results = []
        environment_session = self.open_session(
            session_id=f"{variant_id}:{seed}", services=object()
        )
        try:
            for ordinal, task in enumerate(load_task_manifest()["tasks"]):
                results.append(
                    self._run_task(
                        session, environment_session, task, variant_id, seed, ordinal,
                        memory=memory,
                    )
                )
            self.last_checkpoint = environment_session.checkpoint()
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
        *,
        memory: AgentMemoryPort | None = None,
    ) -> EnvironmentTaskResult:
        task_id = str(task["task_id"])
        goal = str(task["goal"])
        observation = environment_session.observe(None)
        agent_observation = AgentObservation(
            f"{task_id}:observation:{ordinal}",
            f"{variant_id}:{ordinal}",
            dict(observation.payload),
            evidence_payload=dict(observation.payload),
        )
        if memory is None:
            before = session.recall(RecallRequest(goal, None, limit=4))
        else:
            before = memory.recall(
                AgentGoal(
                    task_id,
                    goal,
                    context={"variant_id": variant_id, "seed": seed},
                ),
                agent_observation,
                {},
            )
        action = environment_session.act(
            ActionRequest(f"task:{task_id}", "run_task", {"task_id": task_id}, None)
        )
        if memory is not None:
            memory.record(
                AgentStepReceipt(
                    action.action_id,
                    "run_task",
                    "environment.run_task",
                    f"{variant_id}:{seed}:{task_id}",
                    action.accepted,
                    action.accepted,
                    observation=agent_observation,
                    effect_certainty="confirmed" if action.accepted else "rejected",
                ),
                {},
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
        base_variant = PAPER_METHOD_BASE.get(variant_id, variant_id)
        boost = {
            "no_memory": 0,
            "flat_episodic": 6,
            "fixed_typed": 10,
            "sem": 14,
        }.get(base_variant, 0)
        success = score < 58 + boost
        blocked = not success and score % 2 == 0
        steps = 8 + (int(digest[8:12], 16) % 20)
        reason = "blocked prerequisite" if blocked else "timeout while completing task"
        outcome = MethodTaskOutcome(
            task_id=task_id,
            family=str(task["family"]),
            lineage_id=str(task.get("lineage_id", canonical_digest(task))),
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
            family=str(task["family"]),
        )


class RealMinecraftEnvironment:
    """Real Mineflayer-backed SEM environment.

    The server, bridge state, and evidence roots are supplied by deployment
    configuration; this class never falls back to the scripted fixture.
    """

    environment_id = "minecraft.mineflayer.jsonl.v1"

    def __init__(self, execution_run_id: str | None = None) -> None:
        self.last_checkpoint: bytes | None = None
        self.execution_run_id = (
            execution_run_id
            or os.environ.get("SEM_EXECUTION_RUN_ID", "").strip()
            or uuid4().hex
        )
        if not self.execution_run_id:
            raise ValueError("SEM execution run identity is required")
        self._binding = None
        self._model_binding = None
        self._planner = None
        self._closed = False

    @property
    def identity(self) -> EnvironmentIdentity:
        return EnvironmentIdentity(
            self.environment_id,
            "1.0.0",
            "1",
            "1",
            canonical_digest(
                {
                    "provider": self.environment_id,
                    "host": os.environ.get("MC_HOST", "127.0.0.1"),
                    "port": os.environ.get("MC_PORT", "25565"),
                    "version": os.environ.get("MC_VERSION", "1.21.1"),
                }
            ),
        )

    @property
    def capabilities(self) -> EnvironmentProviderCapabilities:
        return EnvironmentProviderCapabilities((
            EnvironmentCapability.RECONCILE,
            EnvironmentCapability.DIAGNOSTICS,
            EnvironmentCapability.QUERY,
        ))

    def _ensure_environment_binding(self):
        if self._closed:
            raise RuntimeError("real Minecraft environment is closed")
        if self._binding is None:
            recovery_root = os.environ.get(
                "MC_ACTION_RECOVERY_ROOT", "/var/lib/noetrium/action-recovery"
            )
            self._binding = bind_bundled_minecraft_environment(
                host=os.environ.get("MC_HOST", "127.0.0.1"),
                port=int(os.environ.get("MC_PORT", "25565")),
                username=os.environ.get("MC_USERNAME", "ResearchBot"),
                auth=os.environ.get("MC_AUTH", "offline"),
                version=os.environ.get("MC_VERSION", "1.21.1"),
                node_executable=os.environ.get("MC_NODE") or None,
                action_recovery_root=recovery_root,
                connect_timeout_s=float(os.environ.get("MC_CONNECT_TIMEOUT_S", "90")),
                command_timeout_s=float(os.environ.get("MC_COMMAND_TIMEOUT_S", "90")),
                task_group_id=f"sem-minecraft-{self.execution_run_id}",
            )
        return self._binding

    def _ensure_model_planner(self):
        if os.environ.get("SEM_PLANNER_MODE", "model").lower() != "model":
            return None
        if self._planner is not None:
            return self._planner
        closure_path = os.environ.get("SEM_MODEL_QUALIFIED_CLOSURE", "").strip()
        if not closure_path:
            raise RuntimeError(
                "model planner requires SEM_MODEL_QUALIFIED_CLOSURE; "
                "raw SEM_MODEL_BASE_URL fallback is prohibited"
            )
        request_root = os.environ.get(
            "SEM_MODEL_REQUEST_ROOT", "results/model-requests"
        ).strip()
        if not request_root:
            raise RuntimeError("SEM_MODEL_REQUEST_ROOT must be non-empty")
        try:
            self._model_binding = bind_qualified_project_model(
                ModelProviderProfile("sem-qualified", ("generation",)),
                closure_path=closure_path,
                request_root=request_root,
                api_key=os.environ.get("SEM_MODEL_API_KEY", ""),
                task_group_id=f"sem-model-{self.execution_run_id}",
            )
            model_client = self._model_binding.bind(planner_model_requirement())
        except Exception as exc:
            diagnostics = getattr(exc, "diagnostics", ())
            detail = "; ".join(
                str(getattr(item, "message", item)) for item in diagnostics
            )
            if not detail:
                raise
            raise RuntimeError(
                "SEM model qualification preflight failed: "
                f"{detail} (closure={closure_path})"
            ) from exc
        self._planner = ModelActionPlanner(
            model_client,
            self._model_binding.model_requests,
        )
        return self._planner

    def run_suite(
        self,
        *,
        session: SEMMethodSession,
        variant_id: str,
        seed: str,
        assignment: object | None = None,
        assignment_isolation: object | None = None,
        memory: AgentMemoryPort | None = None,
    ) -> tuple[EnvironmentTaskResult, ...]:
        # Admission must succeed before a confirmatory reset mutates the world.
        planner = self._ensure_model_planner()
        if assignment_isolation is None:
            self._reset_assignment_world(session.session_id)
        run_identity = (
            f"{self.execution_run_id}-{session.session_id.replace(':', '-')}"
        )
        binding = self._ensure_environment_binding()
        environment_session = None
        try:
            environment_session = binding.open_session(
                session_id=run_identity,
                services=object(),
            )
            results: list[EnvironmentTaskResult] = []
            for ordinal, task in enumerate(load_task_manifest()["tasks"]):
                task_id = str(task["task_id"])
                started = time.monotonic()
                context = self._execution_context(
                    run_identity=run_identity,
                    task_id=task_id,
                    ordinal=ordinal,
                    environment_generation=binding.identity.artifact_digest,
                    assignment=assignment,
                )
                observation = environment_session.observe(context)
                if not isinstance(observation.payload, Mapping):
                    raise RuntimeError("Noetrium Minecraft observation payload is not a mapping")
                snapshot = dict(observation.payload)
                agent_observation = AgentObservation(
                    f"{task_id}:observation:{ordinal}",
                    f"{variant_id}:{ordinal}",
                    dict(snapshot),
                    evidence_payload=dict(snapshot),
                )
                if memory is None:
                    before = session.recall(
                        RecallRequest(str(task["goal"]), None, limit=4)
                    )
                else:
                    before = memory.recall(
                        AgentGoal(
                            task_id,
                            str(task["goal"]),
                            context={"variant_id": variant_id, "seed": seed},
                        ),
                        agent_observation,
                        {},
                    )
                if planner is not None:
                    plan = planner.plan(
                        task=task,
                        memory_context=before.context_text,
                        snapshot=snapshot,
                        context=context,
                    )
                    if not plan:
                        raise RuntimeError(
                            f"model planner returned an empty plan for task {task_id}"
                        )
                else:
                    plan = load_scripted_action_plan(task)
                task_results = self._run_real_task(
                    environment_session,
                    context,
                    task,
                    task_id,
                    str(task.get("lineage_id", canonical_digest(task))),
                    plan,
                )
                success, failure_class = self._validate_task(task, task_results)
                steps = len(task_results)
                outcome = MethodTaskOutcome(
                    task_id=task_id,
                    family=str(task["family"]),
                    lineage_id=str(task.get("lineage_id", canonical_digest(task))),
                    success=success,
                    utility=1.0 if success else -0.25,
                    steps=steps,
                    failure_reason="" if success else failure_class,
                    memory_queries=1,
                )
                if memory is not None:
                    verified = bool(task_results) and all(
                        bool(item.get("verified")) for item in task_results
                    )
                    memory.record(
                        AgentStepReceipt(
                            f"{run_identity}:{task_id}",
                            "minecraft_task",
                            "minecraft.task",
                            f"{run_identity}:{task_id}",
                            bool(task_results),
                            verified,
                            observation=agent_observation,
                            effect_certainty="confirmed" if verified else "rejected",
                            diagnostics={"action_count": len(task_results)},
                        ),
                        {},
                    )
                session.ingest(
                    {
                        "environment": self.environment_id,
                        "task_id": task_id,
                        "variant_id": variant_id,
                        "seed": seed,
                        "actions": task_results,
                    },
                    None,
                )
                session.task_completed(outcome, None)
                results.append(
                    EnvironmentTaskResult(
                        task_id,
                        success,
                        outcome.utility,
                        steps,
                        time.monotonic() - started,
                        1,
                        failure_class in {"precondition_missing", "provider_rejected"},
                        canonical_digest(
                            {
                                "task_id": task_id,
                                "actions": task_results,
                                "generation": session.generation,
                            }
                        ),
                        failure_class=failure_class,
                        verified_actions=sum(
                            bool(item.get("verified")) for item in task_results
                        ),
                        evidence_closed=bool(task_results) and all(
                            isinstance(item.get("outcome"), Mapping)
                            and (
                                bool(item.get("anchors"))
                                or bool(item.get("outcome", {}).get("evidence"))
                            )
                            for item in task_results
                        ),
                        outcome_codes=tuple(
                            str(item.get("outcome", {}).get("code", ""))
                            for item in task_results
                            if isinstance(item.get("outcome"), Mapping)
                        ),
                    )
                )
            # The live binding currently has no authoritative branch checkpoint
            # provider; keep the slot empty instead of asking the session to
            # fabricate a checkpoint. A deployment-supplied checkpoint provider
            # can populate this field when the world branch authority is bound.
            self.last_checkpoint = None
            return tuple(results)
        finally:
            if environment_session is not None:
                environment_session.close()

    def close(self) -> None:
        if self._closed:
            return
        errors: list[BaseException] = []
        for resource in (self._model_binding, self._binding):
            if resource is None:
                continue
            try:
                resource.close()
            except BaseException as exc:
                errors.append(exc)
        self._closed = True
        if errors:
            raise ExceptionGroup("real Minecraft environment close failed", errors)

    @staticmethod
    def _execution_context(
        *,
        run_identity: str,
        task_id: str,
        ordinal: int,
        environment_generation: str,
        assignment: object | None,
    ) -> ExecutionContext:
        study_id = getattr(assignment, "study_id", None)
        return ExecutionContext(
            run_id=run_identity,
            trace_id=run_identity,
            span_id=f"{run_identity}:{task_id}:{ordinal}",
            study_id=str(study_id) if study_id is not None else None,
            task_id=task_id,
            decision_cycle_id=f"{task_id}:{ordinal}",
            participant_generations=(("environment", environment_generation),),
        )

    @staticmethod
    def _action_event_payload(result: ActionResult) -> dict[str, Any]:
        observation = result.observation
        if observation is None or not isinstance(observation.payload, Mapping):
            raise RuntimeError("Noetrium Minecraft action returned no grounded observation")
        events = observation.payload.get("events", ())
        if not isinstance(events, (list, tuple)):
            raise RuntimeError("Noetrium Minecraft action observation has malformed events")
        for event in reversed(events):
            if not isinstance(event, Mapping) or event.get("kind") != "action_result":
                continue
            payload = event.get("payload")
            if not isinstance(payload, Mapping):
                raise RuntimeError("Noetrium Minecraft action_result payload is malformed")
            materialized = dict(payload)
            materialized.setdefault("verified", result.diagnostics.get("verified"))
            materialized.setdefault("accepted", result.accepted)
            effect = getattr(result, "effect", None)
            if effect is not None:
                certainty = getattr(effect.certainty, "value", effect.certainty)
                effect_payload = {
                    "effect_id": effect.effect_id,
                    "request_digest": effect.request_digest,
                    "certainty": str(certainty),
                    "before_artifact": effect.before_artifact,
                    "after_artifact": effect.after_artifact,
                    "provider_receipt": effect.provider_receipt,
                }
                materialized.setdefault("effect_receipt", effect_payload)
                anchors = materialized.get("anchors")
                if not isinstance(anchors, (list, tuple)) or not anchors:
                    anchors = [f"effect:{effect.effect_id}"]
                    if effect.before_artifact:
                        anchors.append(f"before:{effect.before_artifact}")
                    if effect.after_artifact:
                        anchors.append(f"after:{effect.after_artifact}")
                    materialized["anchors"] = anchors
            return materialized
        raise RuntimeError("Noetrium Minecraft action returned no action_result event")

    def _reset_assignment_world(self, session_id: str) -> None:
        command = os.environ.get("MC_ASSIGNMENT_RESET_COMMAND", "").strip()
        required = os.environ.get("MC_REQUIRE_WORLD_RESET", "0") == "1"
        if not command:
            if required:
                raise RuntimeError(
                    "confirmatory Minecraft run requires MC_ASSIGNMENT_RESET_COMMAND"
                )
            return
        rendered = command.format(
            session_id=session_id.replace(":", "-"),
            assignment_id=session_id.replace(":", "-"),
        )
        completed = run_local_shell_command(rendered, timeout_seconds=300)
        if completed.returncode != 0:
            raise RuntimeError(
                "Minecraft assignment world reset failed: "
                + (completed.stderr or completed.stdout)[-1000:]
            )

    @staticmethod
    def _validate_task(
        task: Mapping[str, Any], actions: list[dict[str, Any]]
    ) -> tuple[bool, str]:
        if not actions:
            return False, "provider_error"
        outcomes = [
            item.get("outcome", {})
            for item in actions
            if isinstance(item.get("outcome"), Mapping)
        ]
        codes = {str(outcome.get("code", "")) for outcome in outcomes}
        if "ACTION_HANDLER_BOUNDED_FAILURE" in codes:
            return False, "timeout"
        if codes & {"NO_RECIPE_OR_CRAFTING_TABLE", "ITEM_NOT_AVAILABLE",
                    "HARVEST_TOOL_REQUIRED", "BLOCK_NOT_FOUND"}:
            return False, "precondition_missing"
        if "PATH_INTERRUPTED" in codes:
            return False, "path_interrupted"
        family = str(task.get("family", ""))
        verified = [item for item in actions if bool(item.get("verified"))]
        if family == "combat_survival" and "NO_THREATS" in codes:
            return False, "no_threats"
        if family == "navigation_return" and "PATH_INTERRUPTED" in codes:
            return False, "path_interrupted"
        if len(verified) != len(actions):
            return False, "partial_effect"
        return True, ""

    def _run_real_task(
        self,
        environment_session: EnvironmentSession,
        context: ExecutionContext,
        task: Mapping[str, Any],
        task_id: str,
        task_lineage: str,
        plan: tuple[tuple[str, Mapping[str, Any], float], ...],
    ) -> list[dict[str, Any]]:
        family = str(task["family"])
        actions: list[tuple[str, dict[str, Any], float]] = list(plan)
        if not actions and os.environ.get("SEM_PLANNER_MODE", "model").lower() == "model":
            raise RuntimeError(f"no executable model plan for task {task_id}")
        if not actions and family == "resource_collection":
            actions = [("collect_block", {"block": "oak_log", "count": 4, "max_distance": 64}, 240.0)]
        elif not actions and family == "crafting_tech_tree":
            actions = [
                ("craft_item", {"item": "oak_planks", "count": 16}, 60.0),
                ("collect_block", {"block": "cobblestone", "count": 3, "max_distance": 32}, 180.0),
                ("craft_item", {"item": "stone_pickaxe", "count": 1}, 90.0),
            ]
        elif not actions and family == "navigation_return":
            actions = [
                ("move_away", {"distance": 16}, 120.0),
                ("goto", {"position": {"x": 9.5, "y": 72, "z": 168.5}, "radius": 5}, 180.0),
            ]
        elif not actions and family == "combat_survival":
            actions = [("defend_self", {"radius": 32, "max_targets": 1, "max_hits": 8}, 180.0)]
        elif not actions and family == "simple_building":
            actions = [
                ("craft_item", {"item": "crafting_table", "count": 1}, 90.0),
                ("craft_item", {"item": "chest", "count": 1}, 90.0),
                ("place_block", {"item": "crafting_table"}, 90.0),
                ("place_block", {"item": "chest"}, 90.0),
            ]
        elif not actions and family == "long_horizon_mixed":
            actions = [
                ("collect_block", {"block": "iron_ore", "count": 1, "max_distance": 64}, 240.0),
                ("craft_item", {"item": "shield", "count": 1}, 120.0),
            ]
        results: list[dict[str, Any]] = []
        for action_ordinal, (action_type, arguments, _planner_timeout_s) in enumerate(actions):
            action_context = context.child(
                span_id=f"{context.span_id}:action:{action_ordinal}",
                operation_id=f"minecraft:{action_type}:{action_ordinal}",
            )
            result = environment_session.act(
                ActionRequest(
                    action_id=f"{context.run_id}:{task_id}:action:{action_ordinal}",
                    action_type=action_type,
                    payload=dict(arguments),
                    context=action_context,
                )
            )
            materialized = self._action_event_payload(result)
            materialized.setdefault("task_id", task_id)
            materialized.setdefault("task_lineage", task_lineage)
            results.append(materialized)
        return results


__all__ = ["EnvironmentTaskResult", "ScriptedMinecraftEnvironment", "RealMinecraftEnvironment"]