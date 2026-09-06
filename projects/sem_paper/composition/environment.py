from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import subprocess
import time
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


class _MinecraftBridgeClient:
    def __init__(self) -> None:
        self.node = os.environ.get("MC_NODE", "/usr/local/bin/node")
        self.script = os.environ.get(
            "MC_BRIDGE_SCRIPT",
            "/opt/noetrium/noetrium_platform/capabilities/environment/minecraft/providers/assets/mineflayer_bridge/bridge.js",
        )
        self.host = os.environ.get("MC_HOST", "127.0.0.1")
        self.port = int(os.environ.get("MC_PORT", "25565"))
        self.version = os.environ.get("MC_VERSION", "1.21.1")
        self.username = os.environ.get("MC_USERNAME", "ResearchBot")
        self.recovery_dir = os.environ.get(
            "MC_ACTION_RECOVERY_DIR", "/var/lib/noetrium/action-recovery"
        )
        self.process: subprocess.Popen[str] | None = None
        self._counter = 0

    def _request(
        self,
        payload: dict[str, Any],
        *,
        wait_kinds: frozenset[str] = frozenset(),
        timeout_s: float = 90.0,
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        if self.process is None or self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("Minecraft bridge is not running")
        self._counter += 1
        request_id = f"sem-real-{self._counter}"
        message = {**payload, "request_id": request_id}
        self.process.stdin.write(json.dumps(message, sort_keys=True) + "\n")
        self.process.stdin.flush()
        ack: dict[str, Any] | None = None
        events: dict[str, dict[str, Any]] = {}
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            line = self.process.stdout.readline()
            if not line:
                stderr = self.process.stderr.read() if self.process.stderr else ""
                raise RuntimeError(f"Minecraft bridge exited: {stderr[-1000:]}")
            value = json.loads(line)
            if value.get("request_id") != request_id:
                continue
            if value.get("type") == "event":
                events[str(value.get("kind"))] = value
            elif value.get("type") == "ack":
                ack = value
            if ack is not None and wait_kinds.issubset(events):
                if ack.get("verified") is False:
                    raise RuntimeError(str(ack.get("error") or ack))
                return ack, events
        raise TimeoutError(f"Minecraft bridge request timed out: {payload.get('cmd')}")

    def start(self) -> None:
        self.process = subprocess.Popen(
            [self.node, self.script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._request(
            {
                "cmd": "connect",
                "host": self.host,
                "port": self.port,
                "username": self.username,
                "auth": "offline",
                "version": self.version,
                "action_recovery_dir": self.recovery_dir,
            },
            wait_kinds=frozenset({"bridge_status", "self_snapshot"}),
            timeout_s=90.0,
        )

    def action(
        self,
        *,
        task_id: str,
        task_lineage: str,
        action_type: str,
        arguments: Mapping[str, Any],
        timeout_s: float,
    ) -> dict[str, Any]:
        self._counter += 1
        action_id = f"sem-real-action-{self._counter}"
        request = {
            "cmd": action_type,
            "action_id": action_id,
            "task_id": task_id,
            "task_lineage": task_lineage,
            "task": task_id,
            **dict(arguments),
            "_action_timeout_ms": max(1000, int(timeout_s * 1000)),
        }
        request["_request_digest"] = hashlib.sha256(
            canonical_bytes(request)
        ).hexdigest()
        _, events = self._request(
            request,
            wait_kinds=frozenset({"action_result"}),
            timeout_s=max(90.0, timeout_s + 30.0),
        )
        result = events["action_result"].get("payload")
        if not isinstance(result, dict):
            raise RuntimeError("Minecraft bridge returned malformed action_result")
        return result

    def close(self) -> None:
        if self.process is None:
            return
        try:
            self._request({"cmd": "quit"}, timeout_s=5.0)
        except Exception:
            self.process.terminate()
        finally:
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None


class RealMinecraftEnvironment:
    """Real Mineflayer-backed SEM environment.

    The server, bridge state, and evidence roots are supplied by deployment
    configuration; this class never falls back to the scripted fixture.
    """

    environment_id = "minecraft.mineflayer.jsonl.v1"

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
        return EnvironmentProviderCapabilities.fully_recoverable()

    def run_suite(
        self,
        *,
        session: SEMMethodSession,
        variant_id: str,
        seed: str,
    ) -> tuple[EnvironmentTaskResult, ...]:
        bridge = _MinecraftBridgeClient()
        bridge.start()
        results: list[EnvironmentTaskResult] = []
        try:
            for ordinal, task in enumerate(load_task_manifest()["tasks"]):
                task_id = str(task["task_id"])
                started = time.monotonic()
                before = session.recall(RecallRequest(str(task["goal"]), None, limit=4))
                task_results = self._run_real_task(
                    bridge, task, task_id, str(task["lineage_id"])
                )
                success = bool(task_results) and all(
                    bool(item.get("verified")) for item in task_results
                )
                steps = len(task_results)
                outcome = MethodTaskOutcome(
                    task_id=task_id,
                    family=str(task["family"]),
                    lineage_id=str(task["lineage_id"]),
                    success=success,
                    utility=(1.0 if success else -0.25) + len(before.artifacts) * 0.01,
                    steps=steps,
                    failure_reason="" if success else "real provider action not verified",
                    memory_queries=1,
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
                        not success,
                        canonical_digest(
                            {
                                "task_id": task_id,
                                "actions": task_results,
                                "generation": session.generation,
                            }
                        ),
                    )
                )
            return tuple(results)
        finally:
            bridge.close()

    def _run_real_task(
        self,
        bridge: _MinecraftBridgeClient,
        task: Mapping[str, Any],
        task_id: str,
        task_lineage: str,
    ) -> list[dict[str, Any]]:
        family = str(task["family"])
        actions: list[tuple[str, dict[str, Any], float]] = []
        if family == "resource_collection":
            actions = [("collect_block", {"block": "oak_log", "count": 4, "max_distance": 64}, 240.0)]
        elif family == "crafting_tech_tree":
            actions = [
                ("craft_item", {"item": "oak_planks", "count": 16}, 60.0),
                ("collect_block", {"block": "cobblestone", "count": 3, "max_distance": 32}, 180.0),
                ("craft_item", {"item": "stone_pickaxe", "count": 1}, 90.0),
            ]
        elif family == "navigation_return":
            actions = [
                ("move_away", {"distance": 16}, 120.0),
                ("goto", {"position": {"x": 9.5, "y": 72, "z": 168.5}, "radius": 5}, 180.0),
            ]
        elif family == "combat_survival":
            actions = [("defend_self", {"radius": 32, "max_targets": 1, "max_hits": 8}, 180.0)]
        elif family == "simple_building":
            actions = [
                ("craft_item", {"item": "crafting_table", "count": 1}, 90.0),
                ("craft_item", {"item": "chest", "count": 1}, 90.0),
                ("place_block", {"item": "crafting_table"}, 90.0),
                ("place_block", {"item": "chest"}, 90.0),
            ]
        elif family == "long_horizon_mixed":
            actions = [
                ("collect_block", {"block": "iron_ore", "count": 1, "max_distance": 64}, 240.0),
                ("craft_item", {"item": "shield", "count": 1}, 120.0),
            ]
        return [
            bridge.action(
                task_id=task_id,
                task_lineage=task_lineage,
                action_type=action_type,
                arguments=arguments,
                timeout_s=timeout_s,
            )
            for action_type, arguments, timeout_s in actions
        ]


__all__ = ["EnvironmentTaskResult", "ScriptedMinecraftEnvironment", "RealMinecraftEnvironment"]