from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
import json

from research_platform.environment.api import (
    ActionRequest,
    Observation,
    StateMachineDynamicsIdentity,
    StateMachineEnvironmentSpec,
    StateTransition,
    JsonValue,
    thaw_json_mapping,
)
from research_platform.experimentation.experiment.api import ExperimentTaskSpec
from research_platform.experimentation.study.api import StudyAssignment, StudyExecutionUnit
from research_platform.experimentation.workload import WorkloadDecision
from research_platform.participant.method.api import MethodSession
from research_platform.platform.kernel import ExecutionContext, canonical_digest, canonical_text

from projects.sem_paper.method.self_evolving_memory.evolution import (
    BranchRole,
    CandidateArchitecture,
)


_POSITIONS: dict[str, dict[str, float]] = {
    "hub": {"x": 0.0, "y": 0.0, "z": 0.0},
    "forest": {"x": 1.0, "y": 0.0, "z": 0.0},
    "quarry": {"x": 0.0, "y": 0.0, "z": 1.0},
    "workshop": {"x": 1.0, "y": 0.0, "z": 1.0},
    "shelter": {"x": 2.0, "y": 0.0, "z": 1.0},
}
_EDGES: dict[str, tuple[str, ...]] = {
    "hub": ("forest", "quarry"),
    "forest": ("hub", "workshop"),
    "quarry": ("hub", "workshop"),
    "workshop": ("forest", "quarry", "shelter"),
    "shelter": ("workshop",),
}
_RESOURCE_LOCATIONS = {"wood": "forest", "stone": "quarry"}
_RECIPES: dict[str, tuple[str, dict[str, int]]] = {
    "planks": ("workshop", {"wood": 1}),
    "marker": ("workshop", {"wood": 1, "stone": 1}),
}
_DYNAMICS_DOCUMENT = {
    "positions": _POSITIONS,
    "edges": _EDGES,
    "resources": _RESOURCE_LOCATIONS,
    "recipes": _RECIPES,
    "transition_contract": "sem-paper.reference-closed-world.v1",
}


@dataclass(frozen=True, slots=True)
class ClosedWorldGoal:
    kind: str
    target: str
    quantity: int = 1

    def __post_init__(self) -> None:
        if self.kind not in {"visit", "collect", "craft"}:
            raise ValueError(f"unsupported closed-world goal kind: {self.kind}")
        if not self.target.strip() or self.quantity <= 0:
            raise ValueError("closed-world goal target and quantity are required")

    @classmethod
    def from_task(cls, task: ExperimentTaskSpec) -> "ClosedWorldGoal":
        try:
            document = json.loads(task.context)
            if not isinstance(document, Mapping):
                raise TypeError("goal context must be a mapping")
            unknown = set(document) - {"kind", "target", "quantity"}
            if unknown:
                raise ValueError(f"unknown closed-world goal fields: {sorted(unknown)}")
            return cls(
                kind=str(document["kind"]),
                target=str(document["target"]),
                quantity=int(document.get("quantity", 1)),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"task {task.task_id} has an invalid closed-world goal context"
            ) from exc


def reference_closed_world_spec() -> StateMachineEnvironmentSpec:
    identity = StateMachineDynamicsIdentity(
        dynamics_id="sem-paper.reference-closed-world.dynamics",
        implementation_version="1",
        artifact_digest=canonical_digest(_DYNAMICS_DOCUMENT),
    )
    return StateMachineEnvironmentSpec(
        environment_id="sem-paper-reference-closed-world",
        dynamics=identity,
        initial_state={
            "location": "hub",
            "position": _POSITIONS["hub"],
            "inventory": {},
            "crafted": [],
            "visited": ["hub"],
            "transition_count": 0,
        },
        action_types=("move", "collect", "craft"),
    )


class ReferenceClosedWorldDynamics:
    """Small deterministic domain used to prove the non-MC production path."""

    identity = reference_closed_world_spec().dynamics

    @staticmethod
    def _reject(state: Mapping[str, JsonValue], code: str) -> StateTransition:
        return StateTransition(state, False, {"code": code})

    def transition(
        self,
        state: Mapping[str, JsonValue],
        request: ActionRequest,
        context: ExecutionContext,
    ) -> StateTransition:
        del context
        current = thaw_json_mapping(state)
        payload = request.payload
        if not isinstance(payload, Mapping):
            raise TypeError("reference closed-world action payload must be a mapping")
        location = str(current["location"])
        inventory = {
            str(name): int(count)
            for name, count in dict(current.get("inventory", {})).items()
        }
        if request.action_type == "move":
            target = str(payload.get("target", ""))
            if target not in _EDGES.get(location, ()):
                return self._reject(current, "not_adjacent")
            current["location"] = target
            current["position"] = dict(_POSITIONS[target])
            visited = [str(item) for item in current.get("visited", [])]
            if target not in visited:
                visited.append(target)
            current["visited"] = visited
        elif request.action_type == "collect":
            resource = str(payload.get("resource", ""))
            if _RESOURCE_LOCATIONS.get(resource) != location:
                return self._reject(current, "resource_not_present")
            inventory[resource] = inventory.get(resource, 0) + 1
            current["inventory"] = inventory
        elif request.action_type == "craft":
            item = str(payload.get("item", ""))
            recipe = _RECIPES.get(item)
            if recipe is None:
                return self._reject(current, "unknown_recipe")
            station, ingredients = recipe
            if location != station:
                return self._reject(current, "wrong_station")
            if any(inventory.get(name, 0) < count for name, count in ingredients.items()):
                return self._reject(current, "missing_ingredient")
            for name, count in ingredients.items():
                inventory[name] -= count
            inventory[item] = inventory.get(item, 0) + 1
            current["inventory"] = inventory
            crafted = [str(value) for value in current.get("crafted", [])]
            crafted.append(item)
            current["crafted"] = crafted
        else:
            raise ValueError(f"unsupported reference action: {request.action_type}")
        current["transition_count"] = int(current["transition_count"]) + 1
        return StateTransition(
            current,
            True,
            {"code": "applied", "location": str(current["location"])},
        )


def _state_mapping(value: Mapping[str, JsonValue], field: str) -> Mapping[str, JsonValue]:
    row = value.get(field, {})
    if not isinstance(row, Mapping):
        raise ValueError(f"closed-world state field is not a mapping: {field}")
    return row


def _shortest_next(source: str, target: str) -> str:
    if source == target:
        return source
    queue: deque[tuple[str, tuple[str, ...]]] = deque([(source, ())])
    seen = {source}
    while queue:
        current, path = queue.popleft()
        for neighbour in _EDGES.get(current, ()):
            if neighbour in seen:
                continue
            next_path = path + (neighbour,)
            if neighbour == target:
                return next_path[0]
            seen.add(neighbour)
            queue.append((neighbour, next_path))
    raise ValueError(f"no reference-world route from {source} to {target}")


class ReferenceClosedWorldPlanner:
    def __init__(self, goal: ClosedWorldGoal) -> None:
        self._goal = goal

    def decide(
        self,
        *,
        task: ExperimentTaskSpec,
        context: ExecutionContext,
        state: Mapping[str, JsonValue],
        memory_context: str,
        step: int,
        prior_actions: tuple[Mapping[str, JsonValue], ...],
    ) -> WorkloadDecision:
        del task, context, memory_context, step, prior_actions
        goal = self._goal
        location = str(state.get("location", ""))
        inventory = _state_mapping(state, "inventory")
        if goal.kind == "visit":
            if location == goal.target:
                return WorkloadDecision("finish", completion_claim=True)
            return WorkloadDecision(
                "move",
                {"target": _shortest_next(location, goal.target)},
                "follow the declared closed-world graph",
            )
        if goal.kind == "collect":
            if int(inventory.get(goal.target, 0)) >= goal.quantity:
                return WorkloadDecision("finish", completion_claim=True)
            resource_location = _RESOURCE_LOCATIONS[goal.target]
            if location != resource_location:
                return WorkloadDecision(
                    "move",
                    {"target": _shortest_next(location, resource_location)},
                    "move to the grounded resource location",
                )
            return WorkloadDecision(
                "collect",
                {"resource": goal.target},
                "collect one grounded resource unit",
            )

        if int(inventory.get(goal.target, 0)) >= goal.quantity:
            return WorkloadDecision("finish", completion_claim=True)
        station, ingredients = _RECIPES[goal.target]
        for resource, count in ingredients.items():
            if int(inventory.get(resource, 0)) >= count:
                continue
            resource_location = _RESOURCE_LOCATIONS[resource]
            if location != resource_location:
                return WorkloadDecision(
                    "move",
                    {"target": _shortest_next(location, resource_location)},
                    "move to a missing ingredient",
                )
            return WorkloadDecision(
                "collect",
                {"resource": resource},
                "collect a recipe ingredient",
            )
        if location != station:
            return WorkloadDecision(
                "move",
                {"target": _shortest_next(location, station)},
                "move to the declared crafting station",
            )
        return WorkloadDecision("craft", {"item": goal.target}, "apply the declared recipe")


class ReferenceClosedWorldPlannerFactory:
    def create(
        self,
        *,
        role: BranchRole,
        candidate: CandidateArchitecture | None,
        unit: StudyExecutionUnit,
        assignment: StudyAssignment,
        task: ExperimentTaskSpec,
        method: MethodSession,
    ) -> ReferenceClosedWorldPlanner:
        del role, candidate, unit, assignment, method
        return ReferenceClosedWorldPlanner(ClosedWorldGoal.from_task(task))


class ReferenceClosedWorldState:
    def state(self, observation: Observation) -> Mapping[str, JsonValue]:
        if not isinstance(observation.payload, Mapping):
            raise ValueError("closed-world observation payload must be a mapping")
        state = observation.payload.get("state")
        if not isinstance(state, Mapping):
            raise ValueError("closed-world observation has no state mapping")
        return state


class ReferenceClosedWorldCompletion:
    def is_complete(
        self,
        *,
        task: ExperimentTaskSpec,
        state: Mapping[str, JsonValue],
        planner_finished: bool,
        last_action: object,
    ) -> bool:
        del planner_finished, last_action
        goal = ClosedWorldGoal.from_task(task)
        if goal.kind == "visit":
            return state.get("location") == goal.target
        inventory = _state_mapping(state, "inventory")
        return int(inventory.get(goal.target, 0)) >= goal.quantity

    def utility(
        self,
        *,
        task: ExperimentTaskSpec,
        success: bool,
        state: Mapping[str, JsonValue],
    ) -> float:
        del task, state
        return 1.0 if success else 0.0


class SEMClosedWorldEvidence:
    """Normalize platform state observations into SEM's grounded evidence schema."""

    def __init__(self, method: MethodSession) -> None:
        self._method = method

    def ingest_observation(
        self,
        observation: Observation,
        context: ExecutionContext,
    ) -> tuple[str, ...]:
        if not isinstance(observation.payload, Mapping):
            raise ValueError("closed-world observation payload must be a mapping")
        state = observation.payload.get("state")
        if not isinstance(state, Mapping):
            raise ValueError("closed-world observation has no state mapping")
        position = state.get("position")
        if not isinstance(position, Mapping):
            raise ValueError("closed-world observation has no grounded position")
        observed_at = f"observation:{observation.observation_id}"
        world_evidence = {
            "event_type": "WORLD_OBSERVATION",
            "entity": "reference-world:agent",
            "position": dict(position),
            "state_text": canonical_text(state),
            "entity_kind": "AGENT_STATE",
            "observed_at": observed_at,
            "occurred_at": observed_at,
            "source_observation_id": observation.observation_id,
        }
        self._method.ingest(world_evidence, context)
        evidence_ids = [
            "cwmem_" + canonical_digest(world_evidence)[:24],
        ]
        if observation.payload.get("kind") == "state_machine_transition":
            action = observation.payload.get("action")
            if not isinstance(action, Mapping):
                raise ValueError("closed-world transition has no action mapping")
            action_evidence = {
                "event_type": "ACTION_RESULT",
                "task": context.task_id or "unscoped-task",
                "context": str(observation.payload.get("state_digest", "")),
                "action": dict(action),
                "outcome": {"accepted": bool(observation.payload.get("accepted", False))},
                "verified": True,
                "occurred_at": observed_at,
                "observed_at": observed_at,
                "source_observation_id": observation.observation_id,
            }
            self._method.ingest(action_evidence, context)
            evidence_ids.append("cwmem_" + canonical_digest(action_evidence)[:24])
        return tuple(evidence_ids)


class SEMClosedWorldEvidenceFactory:
    def create(
        self,
        *,
        role: BranchRole,
        candidate: CandidateArchitecture | None,
        unit: StudyExecutionUnit,
        assignment: StudyAssignment,
        method: MethodSession,
    ) -> SEMClosedWorldEvidence:
        del role, candidate, unit, assignment
        return SEMClosedWorldEvidence(method)


__all__ = [
    "ClosedWorldGoal",
    "ReferenceClosedWorldCompletion",
    "ReferenceClosedWorldDynamics",
    "ReferenceClosedWorldPlanner",
    "ReferenceClosedWorldPlannerFactory",
    "ReferenceClosedWorldState",
    "SEMClosedWorldEvidence",
    "SEMClosedWorldEvidenceFactory",
    "reference_closed_world_spec",
]
