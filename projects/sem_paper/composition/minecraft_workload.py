from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
import math
import re
import time
from typing import Any, Mapping, Protocol, runtime_checkable

from research_platform.environment.api import ActionRequest, ActionResult, EnvironmentSession, Observation
from research_platform.environment.minecraft.api import (
    MinecraftActionOutcomeStatus,
    MinecraftActionResultEvidence,
    MinecraftObservationEvent,
    validate_minecraft_action,
)
from research_platform.experimentation.workload import (
    GenericWorkloadTaskRunner,
    WorkloadBoundaryPort,
    WorkloadCompletionPort,
    WorkloadDecision,
    WorkloadEnvironmentPort,
    WorkloadEvidencePort,
    WorkloadFailurePolicyPort,
    WorkloadPlannerPort,
    WorkloadStatePort,
    WorkloadTaskRunError,
)
from research_platform.participant.method.api import MethodSession, MethodTaskOutcome
from research_platform.experimentation.experiment.api import (
    ExperimentWorkloadFailure,
    ExperimentTaskSpec,
    FailureScope,
    validate_task_graph,
)
from research_platform.experimentation.run.api import RunDiagnosticsPort
from research_platform.participant.agent.api import (
    AgentDiagnosticsPort,
    AgentEvidencePort,
    AgentGoal,
    AgentLoopCheckpoint,
    AgentLoopResult,
    AgentMemoryPort,
    AgentObservation,
    AgentStepReceipt,
    AgentPlannerPort,
    AgentProgressPort,
)
from research_platform.platform.kernel import ExecutionContext, JsonObject, JsonValue, canonical_digest
from research_platform.platform.kernel.errors import describe_exception


class PrimaryTaskFamily(StrEnum):
    """Frozen primary Minecraft workload families for the SEM study."""

    RESOURCE_COLLECTION = "resource_collection"
    CRAFTING_TECH_TREE = "crafting_tech_tree"
    NAVIGATION_RETURN = "navigation_return"
    COMBAT_SURVIVAL = "combat_survival"
    SIMPLE_BUILDING = "simple_building"
    LONG_HORIZON_MIXED = "long_horizon_mixed"


PRIMARY_TASK_FAMILIES = tuple(item.value for item in PrimaryTaskFamily)


@dataclass(frozen=True, slots=True)
class _BlueprintCellRequirement:
    offset: tuple[int, int, int]
    block: str


@dataclass(frozen=True, slots=True)
class _BlueprintConstraint:
    anchor: str
    cells: tuple[_BlueprintCellRequirement, ...]


def _blueprint_constraint(params: JsonObject) -> _BlueprintConstraint:
    if set(params) != {"anchor", "blocks"}:
        raise ValueError("blueprint_complete requires exactly anchor and blocks")
    anchor = params.get("anchor")
    blocks = params.get("blocks")
    if not isinstance(anchor, str) or not anchor.strip():
        raise ValueError("blueprint_complete anchor must be a non-empty string")
    if not isinstance(blocks, (list, tuple)) or not blocks:
        raise ValueError("blueprint_complete blocks must be non-empty")
    cells: list[_BlueprintCellRequirement] = []
    seen: set[tuple[int, int, int]] = set()
    for row in blocks:
        if not isinstance(row, Mapping) or set(row) != {"offset", "block"}:
            raise ValueError("blueprint block rows require exactly offset and block")
        offset = row.get("offset")
        block = row.get("block")
        if not isinstance(offset, Mapping) or set(offset) != {"x", "y", "z"}:
            raise ValueError("blueprint block offset requires exactly x/y/z")
        coords: list[int] = []
        for axis in ("x", "y", "z"):
            value = offset.get(axis)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("blueprint offsets must be finite integers")
            numeric = float(value)
            if not math.isfinite(numeric) or int(numeric) != numeric:
                raise ValueError("blueprint offsets must be finite integers")
            coords.append(int(numeric))
        key = tuple(coords)
        if key in seen:
            raise ValueError("blueprint offsets must be unique")
        if not isinstance(block, str) or not block.strip():
            raise ValueError("blueprint block must be a non-empty string")
        seen.add(key)
        cells.append(_BlueprintCellRequirement(key, block.strip()))
    return _BlueprintConstraint(anchor.strip(), tuple(cells))


@dataclass(frozen=True, slots=True)
class MinecraftSuccessSpec:
    kind: str
    params: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        allowed = {
            "always",
            "planner_finish",
            "last_action_verified",
            "inventory_min",
            "near_anchor",
            "health_positive",
            "observed_entity",
            "blueprint_complete",
            "away_then_return",
            "combat_survived",
        }
        if self.kind not in allowed:
            raise ValueError(f"unknown Minecraft success kind: {self.kind}")
        if not isinstance(self.params, Mapping):
            raise TypeError("Minecraft success params must be a mapping")
        if self.kind == "inventory_min" and not str(self.params.get("item", "")).strip():
            raise ValueError("inventory_min success requires item")
        if self.kind == "inventory_min":
            try:
                count = int(self.params.get("count", 1))
            except (TypeError, ValueError) as exc:
                raise ValueError("inventory_min count must be an integer") from exc
            if count <= 0:
                raise ValueError("inventory_min count must be positive")
        if self.kind == "near_anchor" and not str(self.params.get("anchor", "")).strip():
            raise ValueError("near_anchor success requires anchor")
        if self.kind == "near_anchor":
            try:
                radius = float(self.params.get("radius", 3))
            except (TypeError, ValueError) as exc:
                raise ValueError("near_anchor radius must be numeric") from exc
            if not math.isfinite(radius) or radius < 0:
                raise ValueError("near_anchor radius must be finite and non-negative")
        if self.kind == "observed_entity" and not str(self.params.get("entity", "")).strip():
            raise ValueError("observed_entity success requires entity")
        if self.kind == "blueprint_complete":
            _blueprint_constraint(self.params)
        if self.kind == "away_then_return":
            anchor = self.params.get("anchor")
            if not isinstance(anchor, str) or not anchor.strip():
                raise ValueError("away_then_return requires anchor")
            departure = float(self.params.get("min_departure_distance", 0))
            radius = float(self.params.get("return_radius", 0))
            if not math.isfinite(departure) or not math.isfinite(radius) or radius <= 0 or departure <= radius:
                raise ValueError("away_then_return requires finite departure distance greater than positive return radius")
        if self.kind == "combat_survived":
            count = self.params.get("min_verified_combat_actions", 1)
            if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
                raise ValueError("combat_survived requires a positive integer min_verified_combat_actions")


@dataclass(frozen=True, slots=True)
class MinecraftTaskSpec:
    task_id: str
    family: str
    goal: str
    context: str = ""
    lineage_id: str = ""
    referenced_anchors: tuple[str, ...] = ()
    depends_on_task_ids: tuple[str, ...] = ()
    retry_of_task_id: str | None = None
    max_steps: int = 12
    max_seconds: float = 180.0
    success: MinecraftSuccessSpec = MinecraftSuccessSpec("planner_finish", {})
    script: tuple[JsonObject, ...] = ()

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.goal.strip() or not self.family.strip():
            raise ValueError("Minecraft task identity, family and goal are required")
        if not self.lineage_id.strip():
            object.__setattr__(self, "lineage_id", self.task_id)
        if isinstance(self.max_steps, bool) or not isinstance(self.max_steps, int) or self.max_steps <= 0:
            raise ValueError("Minecraft task max_steps must be a positive integer")
        if not isinstance(self.max_seconds, (int, float)) or isinstance(self.max_seconds, bool) or not math.isfinite(self.max_seconds) or self.max_seconds <= 0:
            raise ValueError("Minecraft task limits must be positive")
        if len(set(self.referenced_anchors)) != len(self.referenced_anchors):
            raise ValueError("Minecraft task referenced_anchors must be unique")
        if len(set(self.depends_on_task_ids)) != len(self.depends_on_task_ids):
            raise ValueError("Minecraft task dependencies must be unique")
        if self.task_id in self.depends_on_task_ids or self.retry_of_task_id == self.task_id:
            raise ValueError("Minecraft task cannot depend on or retry itself")

    def as_experiment_task(self) -> ExperimentTaskSpec:
        """Expose the generic task identity without exporting MC success rules."""

        return ExperimentTaskSpec(
            task_id=self.task_id,
            family=self.family,
            objective=self.goal,
            context=self.context,
            lineage_id=self.lineage_id,
            depends_on_task_ids=self.depends_on_task_ids,
            retry_of_task_id=self.retry_of_task_id,
            max_steps=self.max_steps,
            max_seconds=self.max_seconds,
        )


def task_from_mapping(raw: JsonObject) -> MinecraftTaskSpec:
    success_raw = raw.get("success", {"kind": "planner_finish"})
    if isinstance(success_raw, str):
        success = MinecraftSuccessSpec(success_raw, {})
    elif isinstance(success_raw, Mapping):
        success = MinecraftSuccessSpec(
            str(success_raw.get("kind", "planner_finish")),
            {key: value for key, value in success_raw.items() if key != "kind"},
        )
    else:
        raise ValueError("Minecraft task success must be a string or mapping")
    raw_script = raw.get("script", ())
    if not isinstance(raw_script, (list, tuple)):
        raise ValueError("Minecraft task script must be a list or tuple")
    script: list[JsonObject] = []
    for value in raw_script:
        if not isinstance(value, Mapping):
            raise ValueError("Minecraft task script rows must be mappings")
        if set(value) - {"tool", "args"}:
            raise ValueError("Minecraft task script rows may contain only tool and args")
        tool = str(value.get("tool", "")).strip()
        args = value.get("args", {})
        if not tool or not isinstance(args, Mapping):
            raise ValueError("Minecraft task script requires a tool and mapping args")
        normalized_args = (
            dict(args)
            if tool == "finish"
            else validate_minecraft_action(tool, args)
        )
        script.append({"tool": tool, "args": normalized_args})
    return MinecraftTaskSpec(
        task_id=str(raw["task_id"]),
        family=str(raw.get("family", "mixed")),
        goal=str(raw["goal"]),
        context=str(raw.get("context", "")),
        lineage_id=str(raw.get("lineage_id", raw["task_id"])),
        referenced_anchors=_string_sequence(raw.get("referenced_anchors", ()), "referenced_anchors"),
        depends_on_task_ids=_string_sequence(raw.get("depends_on_task_ids", ()), "depends_on_task_ids"),
        retry_of_task_id=str(raw["retry_of_task_id"]) if raw.get("retry_of_task_id") else None,
        max_steps=int(raw.get("max_steps", 12)),
        max_seconds=float(raw.get("max_seconds", 180.0)),
        success=success,
        script=tuple(script),
    )


def _string_sequence(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"Minecraft task {field_name} must be a list or tuple")
    values = tuple(str(item).strip() for item in value)
    if any(not item for item in values):
        raise ValueError(f"Minecraft task {field_name} cannot contain empty values")
    return values


def minecraft_task_manifest_digest(tasks: tuple[MinecraftTaskSpec, ...]) -> str:
    """Bind the full scientific task contract, including success/evidence semantics."""

    return canonical_digest(tuple({
        "task": task.as_experiment_task(),
        "referenced_anchors": task.referenced_anchors,
        "success": {"kind": task.success.kind, **dict(task.success.params)},
        "script": task.script,
    } for task in tasks))


def validate_task_manifest(
    tasks: tuple[MinecraftTaskSpec, ...],
    *,
    selected_ids: tuple[str, ...] = (),
) -> tuple[MinecraftTaskSpec, ...]:
    """Validate task graph identity and return a deterministic dependency order."""

    if not tasks:
        raise ValueError("Minecraft task manifest is empty")
    generic_tasks = tuple(task.as_experiment_task() for task in tasks)
    ordered_generic = validate_task_graph(generic_tasks, selected_ids=selected_ids)
    by_id: dict[str, MinecraftTaskSpec] = {task.task_id: task for task in tasks}
    return tuple(by_id[task.task_id] for task in ordered_generic)


def validate_primary_task_manifest(
    tasks: tuple[MinecraftTaskSpec, ...],
    *,
    selected_ids: tuple[str, ...] = (),
) -> tuple[MinecraftTaskSpec, ...]:
    """Validate the frozen six-family primary matrix."""

    full_ordered = validate_task_manifest(tasks)
    families = {task.family for task in full_ordered}
    missing = sorted(set(PRIMARY_TASK_FAMILIES) - families)
    if missing:
        raise ValueError(
            "primary Minecraft task manifest is missing families: " + ", ".join(missing)
        )
    unexpected = sorted(families - set(PRIMARY_TASK_FAMILIES))
    if unexpected:
        raise ValueError(
            "primary Minecraft task manifest contains non-primary families: "
            + ", ".join(unexpected)
        )
    if len(full_ordered) != len(PRIMARY_TASK_FAMILIES) or len(families) != len(full_ordered):
        raise ValueError("primary Minecraft task manifest must contain exactly one task per primary family")
    expected_success = {
        PrimaryTaskFamily.RESOURCE_COLLECTION.value: "inventory_min",
        PrimaryTaskFamily.CRAFTING_TECH_TREE.value: "inventory_min",
        PrimaryTaskFamily.NAVIGATION_RETURN.value: "away_then_return",
        PrimaryTaskFamily.COMBAT_SURVIVAL.value: "combat_survived",
        PrimaryTaskFamily.SIMPLE_BUILDING.value: "blueprint_complete",
        PrimaryTaskFamily.LONG_HORIZON_MIXED.value: "inventory_min",
    }
    for task in full_ordered:
        expected = expected_success[task.family]
        if task.success.kind != expected:
            raise ValueError(f"primary Minecraft family {task.family} requires success kind {expected}")
        if task.family == PrimaryTaskFamily.SIMPLE_BUILDING.value:
            constraint = _blueprint_constraint(task.success.params)
            if constraint.anchor not in task.referenced_anchors:
                raise ValueError("primary simple_building must reference its blueprint anchor")
    return validate_task_manifest(tasks, selected_ids=selected_ids)


@dataclass(frozen=True, slots=True)
class MinecraftEnvironmentObservation:
    """Project-facing view produced by a composition adapter around MC Observation."""

    observation_id: str
    state: JsonObject
    payload: JsonValue


@dataclass(frozen=True, slots=True)
class MinecraftEnvironmentActionResult:
    accepted: bool
    verified: bool | None
    observation: MinecraftEnvironmentObservation | None
    payload: JsonValue = None
    diagnostics: JsonObject = field(default_factory=dict)


class MinecraftWorkloadEnvironmentPort(Protocol):
    def observe(self, context: ExecutionContext) -> MinecraftEnvironmentObservation: ...

    def act(
        self,
        action_id: str,
        action_type: str,
        payload: JsonObject,
        context: ExecutionContext,
    ) -> MinecraftEnvironmentActionResult: ...


@runtime_checkable
class MinecraftWorkloadBoundaryPort(Protocol):
    """Optional task-boundary capability, independent of observe/act state IO."""

    def begin_task(
        self,
        metadata: JsonObject,
        context: ExecutionContext,
    ) -> MinecraftEnvironmentObservation | None: ...

    def end_task(
        self,
        metadata: JsonObject,
        context: ExecutionContext,
    ) -> MinecraftEnvironmentObservation | None: ...


@dataclass(frozen=True, slots=True)
class MinecraftPlannerDecision:
    action_type: str
    payload: JsonObject = field(default_factory=dict)
    rationale: str = ""


class MinecraftPlannerPort(Protocol):
    def decide(
        self,
        *,
        task: MinecraftTaskSpec,
        context: ExecutionContext,
        state: JsonObject,
        memory_context: str,
        step: int,
        prior_actions: tuple[JsonObject, ...],
    ) -> MinecraftPlannerDecision: ...


class MinecraftCognitionRunnerPort(Protocol):
    def run(
        self,
        goal: AgentGoal,
        context: ExecutionContext,
        *,
        session_id: str,
        checkpoint: AgentLoopCheckpoint | None = None,
    ) -> AgentLoopResult: ...


class MinecraftCognitionCheckpointPort(Protocol):
    """Binding-owned cognition state included in workload checkpoints."""

    def checkpoint_for(self, task_id: str) -> AgentLoopCheckpoint | None: ...

    def progress_for(self, task_id: str) -> AgentProgressPort: ...


class MinecraftCognitionFactoryPort(Protocol):
    def create(
        self,
        *,
        session: EnvironmentSession,
        planner: AgentPlannerPort,
        evidence: AgentEvidencePort,
        progress: AgentProgressPort,
        memory: AgentMemoryPort | None,
        diagnostics: AgentDiagnosticsPort | None,
    ) -> MinecraftCognitionRunnerPort: ...


class MinecraftEvidencePort(Protocol):
    def ingest_observation(self, observation: JsonValue, context: ExecutionContext) -> tuple[str, ...]: ...


class MinecraftWorkloadDiagnosticsPort(RunDiagnosticsPort, Protocol):
    """MC name for the platform run diagnostics contract."""

    pass


class MinecraftWorkloadFailure(ExperimentWorkloadFailure):
    """MC adapter failure classified by the generic workload failure scope."""

    def __init__(
        self,
        phase: str,
        code: str,
        message: str,
        *,
        scope: FailureScope = FailureScope.TASK,
    ) -> None:
        super().__init__(phase, code, message, scope=scope)


class _MinecraftFailurePolicy(WorkloadFailurePolicyPort):
    """The MC adapter refuses to continue after an unproven branch transition."""

    def scope(self, phase: str, exception: BaseException) -> FailureScope:
        del phase, exception
        return FailureScope.BRANCH


@dataclass(frozen=True, slots=True)
class MinecraftTaskRunResult:
    task_id: str
    family: str
    success: bool
    utility: float
    steps: int
    duration_s: float
    lineage_id: str = ""
    failure_reason: str = ""
    memory_queries: int = 0
    planner_actions: tuple[JsonObject, ...] = ()
    decision_cycles: tuple[JsonObject, ...] = ()
    completion_receipt: JsonValue | None = None
    blocked: bool = False
    failure_scope: str = FailureScope.TASK.value
    diagnostics: JsonObject = field(default_factory=dict)


def _item_match(name: str, query: str) -> bool:
    if query.startswith("re:"):
        return re.search(query[3:], name) is not None
    return name == query or query in name


def evaluate_success(
    task: MinecraftTaskSpec,
    state: JsonObject,
    *,
    planner_finished: bool,
) -> bool:
    kind = task.success.kind
    params = dict(task.success.params)
    if kind == "always":
        return True
    if kind == "planner_finish":
        # ``finish`` is only a planner intent.  A scientific task may complete
        # on that intent only when the environment state independently proves
        # the preceding action was verified.  Missing/unknown evidence is not
        # success.
        return planner_finished and state.get("last_action_verified") is True
    if kind == "last_action_verified":
        return state.get("last_action_verified") is True
    if kind == "inventory_min":
        inventory = state.get("inventory", {})
        if not isinstance(inventory, Mapping):
            return False
        query = str(params["item"])
        required = int(params.get("count", 1))
        return sum(int(value) for key, value in inventory.items() if _item_match(str(key), query)) >= required
    if kind == "near_anchor":
        anchors = state.get("anchors", {})
        position = state.get("position")
        anchor = anchors.get(str(params["anchor"])) if isinstance(anchors, Mapping) else None
        if not isinstance(anchor, Mapping) or not isinstance(position, Mapping):
            return False
        try:
            distance = math.sqrt(sum((float(position[key]) - float(anchor[key])) ** 2 for key in ("x", "y", "z")))
        except (KeyError, TypeError, ValueError):
            return False
        return distance <= float(params.get("radius", 3))
    if kind == "health_positive":
        try:
            return float(state["health"]) > 0
        except (KeyError, TypeError, ValueError):
            return False
    if kind in {"blueprint_complete", "away_then_return", "combat_survived"}:
        # Historical/receipt success predicates cannot be proven from one
        # compact final state projection alone.
        return False
    if kind == "observed_entity":
        entities = state.get("nearby_entities", ())
        if not isinstance(entities, (list, tuple)):
            return False
        query = str(params.get("entity", "")).lower()
        return any(
            query in " ".join(str(row.get(key, "")).lower() for key in ("name", "mob_type", "type", "username"))
            for row in entities
            if isinstance(row, Mapping)
        )
    raise ValueError(f"unknown Minecraft success kind: {kind}")


def _block_coordinates(value: JsonValue) -> tuple[int, int, int] | None:
    if not isinstance(value, Mapping) or set(value) != {"x", "y", "z"}:
        return None
    coords: list[int] = []
    for axis in ("x", "y", "z"):
        raw = value.get(axis)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None
        numeric = float(raw)
        if not math.isfinite(numeric) or int(numeric) != numeric:
            return None
        coords.append(int(numeric))
    return tuple(coords)


def _receipt_action_result(
    receipt: AgentStepReceipt,
) -> tuple[MinecraftActionResultEvidence, JsonObject] | None:
    observation = receipt.observation
    if observation is None or not isinstance(observation.evidence_payload, Mapping):
        return None
    events = observation.evidence_payload.get("events")
    if not isinstance(events, (list, tuple)):
        return None
    for raw in events:
        if not isinstance(raw, Mapping) or raw.get("kind") != "action_result":
            continue
        payload = raw.get("payload")
        if not isinstance(payload, Mapping) or payload.get("action_id") != receipt.action_id:
            continue
        sequence = raw.get("sequence", 0)
        timestamp_ms = raw.get("timestamp_ms", 0)
        if isinstance(sequence, bool) or not isinstance(sequence, int):
            return None
        if isinstance(timestamp_ms, bool) or not isinstance(timestamp_ms, int):
            return None
        source = raw.get("source", "mineflayer")
        request_id = raw.get("request_id")
        if not isinstance(source, str) or (request_id is not None and not isinstance(request_id, str)):
            return None
        event = MinecraftObservationEvent(
            "action_result",
            dict(payload),
            sequence=sequence,
            timestamp_ms=timestamp_ms,
            source=source,
            request_id=request_id,
        )
        try:
            evidence = MinecraftActionResultEvidence.from_event(
                event,
                expected_action_id=receipt.action_id,
                expected_action_type=receipt.action_type,
            )
        except ValueError:
            return None
        action = payload.get("action")
        if not isinstance(action, Mapping):
            return None
        return evidence, dict(action)
    return None


def _anchor_coordinates(
    anchor: str,
    final_observation: AgentObservation,
    receipts: tuple[AgentStepReceipt, ...],
) -> tuple[int, int, int] | None:
    observations = (final_observation,) + tuple(
        receipt.observation
        for receipt in reversed(receipts)
        if receipt.observation is not None
    )
    for observation in observations:
        anchors = observation.state.get("anchors")
        value = anchors.get(anchor) if isinstance(anchors, Mapping) else None
        if not isinstance(value, Mapping):
            continue
        coords: list[int] = []
        valid = True
        for axis in ("x", "y", "z"):
            raw = value.get(axis)
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                valid = False
                break
            numeric = float(raw)
            if not math.isfinite(numeric):
                valid = False
                break
            coords.append(math.floor(numeric))
        if valid:
            return tuple(coords)
    return None


def _blueprint_complete_from_receipts(
    task: MinecraftTaskSpec,
    receipts: tuple[AgentStepReceipt, ...],
    final_observation: AgentObservation,
) -> bool:
    constraint = _blueprint_constraint(task.success.params)
    base = _anchor_coordinates(constraint.anchor, final_observation, receipts)
    if base is None:
        return False
    expected = {
        tuple(base[index] + cell.offset[index] for index in range(3)): cell.block
        for cell in constraint.cells
    }
    known: dict[tuple[int, int, int], str | None] = {}
    for receipt in receipts:
        parsed = _receipt_action_result(receipt)
        if parsed is None:
            continue
        evidence, action = parsed
        outcome = evidence.outcome
        if receipt.action_type == "place_block":
            coords = _block_coordinates(outcome.get("position"))
            placed = outcome.get("placed")
            requested = action.get("item")
            if (
                coords in expected
                and receipt.verified is True
                and evidence.verified is True
                and evidence.status is MinecraftActionOutcomeStatus.APPLIED
                and outcome.get("code") == "BLOCK_PLACED"
                and isinstance(placed, str)
                and isinstance(requested, str)
                and requested == placed
            ):
                known[coords] = placed
        elif receipt.action_type == "collect_block":
            broken = outcome.get("broken")
            if not isinstance(broken, (list, tuple)):
                continue
            for row in broken:
                if not isinstance(row, Mapping):
                    continue
                coords = _block_coordinates(row.get("position"))
                if coords in expected:
                    known[coords] = None
    return all(known.get(coords) == block for coords, block in expected.items())


def _position_distance(position: object, anchor: tuple[int, int, int]) -> float | None:
    if not isinstance(position, Mapping):
        return None
    try:
        values = tuple(float(position[axis]) for axis in ("x", "y", "z"))
    except (KeyError, TypeError, ValueError):
        return None
    if any(not math.isfinite(value) for value in values):
        return None
    return math.sqrt(sum((values[index] - anchor[index]) ** 2 for index in range(3)))


def _away_then_return_from_receipts(task: MinecraftTaskSpec, result: AgentLoopResult) -> bool:
    params = task.success.params
    anchor_name = str(params["anchor"])
    base = _anchor_coordinates(anchor_name, result.final_observation, result.action_receipts)
    if base is None:
        return False
    departure = float(params["min_departure_distance"])
    return_radius = float(params["return_radius"])
    movement = {"goto", "goto_entity", "move_away", "follow_player"}
    departed = False
    returned = False
    for receipt in result.action_receipts:
        if receipt.action_type not in movement or receipt.verified is not True:
            continue
        parsed = _receipt_action_result(receipt)
        if parsed is None or parsed[0].status is not MinecraftActionOutcomeStatus.APPLIED or parsed[0].verified is not True:
            continue
        distance = _position_distance(receipt.observation.state.get("position") if receipt.observation else None, base)
        if distance is None:
            continue
        if not departed and distance >= departure:
            departed = True
        elif departed and distance <= return_radius:
            returned = True
    final_distance = _position_distance(result.final_observation.state.get("position"), base)
    return departed and returned and final_distance is not None and final_distance <= return_radius


def _combat_survived_from_receipts(task: MinecraftTaskSpec, result: AgentLoopResult) -> bool:
    try:
        health = float(result.final_observation.state.get("health", 0))
    except (TypeError, ValueError):
        return False
    if not math.isfinite(health) or health <= 0:
        return False
    required = int(task.success.params.get("min_verified_combat_actions", 1))
    meaningful = 0
    for receipt in result.action_receipts:
        if receipt.verified is not True or receipt.action_type not in {"attack_nearest", "attack_entity", "ranged_attack", "defend_self"}:
            continue
        parsed = _receipt_action_result(receipt)
        if parsed is None:
            continue
        evidence = parsed[0]
        if evidence.status is not MinecraftActionOutcomeStatus.APPLIED or evidence.verified is not True:
            continue
        code = evidence.outcome.get("code")
        if receipt.action_type == "defend_self":
            targets = evidence.outcome.get("targets_observed", 0)
            if code == "AREA_SECURED" and isinstance(targets, int) and not isinstance(targets, bool) and targets > 0:
                meaningful += 1
        elif code in {"TARGET_DEFEATED", "TARGET_HIT_CONFIRMED"}:
            meaningful += 1
    return meaningful >= required


def evaluate_cognition_success(task: MinecraftTaskSpec, result: AgentLoopResult) -> bool:
    if task.success.kind == "blueprint_complete":
        return _blueprint_complete_from_receipts(
            task,
            result.action_receipts,
            result.final_observation,
        )
    if task.success.kind == "away_then_return":
        return _away_then_return_from_receipts(task, result)
    if task.success.kind == "combat_survived":
        return _combat_survived_from_receipts(task, result)
    return evaluate_success(
        task,
        dict(result.final_observation.state),
        planner_finished=result.success,
    )


class ScriptedMinecraftPlanner:
    """Project workload adapter for deterministic baseline/smoke scripts."""

    def __init__(self, script: tuple[JsonObject, ...]) -> None:
        self._script = script

    def decide(
        self,
        *,
        task: MinecraftTaskSpec,
        context: ExecutionContext,
        state: JsonObject,
        memory_context: str,
        step: int,
        prior_actions: tuple[JsonObject, ...],
    ) -> MinecraftPlannerDecision:
        del task, context, state, memory_context, prior_actions
        if step >= len(self._script):
            return MinecraftPlannerDecision("finish", {"reason": "script_exhausted"}, "scripted")
        row = self._script[step]
        action_type = str(row["tool"])
        payload = row.get("args", {})
        if not isinstance(payload, Mapping):
            raise ValueError("scripted Minecraft planner args must be a mapping")
        return MinecraftPlannerDecision(action_type, dict(payload), "scripted")


class _MinecraftGenericEnvironment(WorkloadEnvironmentPort):
    """Adapter from the Paper MC workload ABI to the platform environment ABI."""

    def __init__(self, source: MinecraftWorkloadEnvironmentPort) -> None:
        self._source = source

    @staticmethod
    def _observation(value: MinecraftEnvironmentObservation) -> Observation:
        return Observation(
            value.observation_id,
            "minecraft",
            {"state": dict(value.state), "raw": value.payload},
        )

    def observe(self, context: ExecutionContext) -> Observation:
        return self._observation(self._source.observe(context))

    def act(self, request: ActionRequest) -> ActionResult:
        result = self._source.act(
            request.action_id,
            request.action_type,
            dict(request.payload) if isinstance(request.payload, Mapping) else {},
            request.context,
        )
        observation = None if result.observation is None else self._observation(result.observation)
        diagnostics = dict(result.diagnostics)
        if result.verified is not None:
            diagnostics["verified"] = result.verified
        return ActionResult(request.action_id, result.accepted, observation, None, diagnostics)



class _MinecraftBoundaryAdapter(WorkloadBoundaryPort):
    """Keep MC task-boundary events at the project/environment adapter seam."""

    def __init__(self, source: MinecraftWorkloadBoundaryPort) -> None:
        self._source = source

    def begin(self, metadata: JsonObject, context: ExecutionContext) -> Observation | None:
        value = self._source.begin_task(metadata, context)
        return None if value is None else _MinecraftGenericEnvironment._observation(value)

    def end(self, metadata: JsonObject, context: ExecutionContext) -> Observation | None:
        value = self._source.end_task(metadata, context)
        return None if value is None else _MinecraftGenericEnvironment._observation(value)


class _MinecraftStateProjection(WorkloadStatePort):
    def state(self, observation: Observation) -> JsonObject:
        payload = observation.payload
        if not isinstance(payload, Mapping) or not isinstance(payload.get("state"), Mapping):
            raise TypeError("MC workload observation state must be a mapping")
        return dict(payload["state"])


class _MinecraftEvidenceAdapter(WorkloadEvidencePort):
    def __init__(self, source: MinecraftEvidencePort) -> None:
        self._source = source

    def ingest_observation(self, observation: Observation, context: ExecutionContext) -> tuple[str, ...]:
        payload = observation.payload
        if not isinstance(payload, Mapping) or not isinstance(payload.get("state"), Mapping):
            raise TypeError("MC evidence observation is missing a mapping state")
        value = MinecraftEnvironmentObservation(
            observation.observation_id,
            dict(payload["state"]),
            payload.get("raw"),
        )
        return self._source.ingest_observation(value, context)


class _MinecraftPlannerAdapter(WorkloadPlannerPort):
    def __init__(self, source: MinecraftPlannerPort, tasks: Mapping[str, MinecraftTaskSpec]) -> None:
        self._source = source
        self._tasks = tasks

    def decide(
        self,
        *,
        task: ExperimentTaskSpec,
        context: ExecutionContext,
        state: JsonObject,
        memory_context: str,
        step: int,
        prior_actions: tuple[JsonObject, ...],
    ) -> WorkloadDecision:
        source_task = self._tasks[task.task_id]
        decision = self._source.decide(
            task=source_task,
            context=context,
            state=state,
            memory_context=memory_context,
            step=step,
            prior_actions=prior_actions,
        )
        return WorkloadDecision(
            decision.action_type,
            dict(decision.payload),
            decision.rationale,
            completion_claim=decision.action_type == "finish",
        )


class _MinecraftCompletionAdapter(WorkloadCompletionPort):
    def __init__(self, tasks: Mapping[str, MinecraftTaskSpec]) -> None:
        self._tasks = tasks

    def is_complete(
        self,
        *,
        task: ExperimentTaskSpec,
        state: JsonObject,
        planner_finished: bool,
        last_action: ActionResult | None,
    ) -> bool:
        source_task = self._tasks[task.task_id]
        if source_task.success.kind == "planner_finish":
            verified = (
                last_action.diagnostics.get("verified")
                if last_action is not None and isinstance(last_action.diagnostics, Mapping)
                else None
            )
            return bool(
                planner_finished
                and last_action is not None
                and last_action.accepted
                and verified is True
            )
        return evaluate_success(source_task, state, planner_finished=planner_finished)

    def utility(self, *, task: ExperimentTaskSpec, success: bool, state: JsonObject) -> float:
        del task, state
        return 1.0 if success else 0.0


class _MinecraftActionAdapter:
    def action_id(self, task: ExperimentTaskSpec, step: int) -> str:
        return f"{task.task_id}:action:{step}"


class _CognitionProgressCapture(AgentProgressPort):
    def __init__(self) -> None:
        self.latest: AgentLoopCheckpoint | None = None

    def persist(self, checkpoint: AgentLoopCheckpoint, context: ExecutionContext) -> None:
        del context
        self.latest = checkpoint


class MinecraftWorkloadRunner:
    """MC adapter over the platform-owned generic workload runner."""

    def __init__(
        self,
        *,
        environment: MinecraftWorkloadEnvironmentPort,
        method: MethodSession,
        evidence: MinecraftEvidencePort,
        planner: MinecraftPlannerPort,
        diagnostics: MinecraftWorkloadDiagnosticsPort | None = None,
        cognition_factory: MinecraftCognitionFactoryPort | None = None,
        cognition_checkpoints: MinecraftCognitionCheckpointPort | None = None,
        max_diagnostic_errors: int = 64,
    ) -> None:
        task_lookup: dict[str, MinecraftTaskSpec] = {}
        self.environment = environment
        self.method = method
        self.evidence = evidence
        self.planner = planner
        self.diagnostics = diagnostics
        self.cognition_factory = cognition_factory
        self.cognition_checkpoints = cognition_checkpoints
        self.max_diagnostic_errors = max_diagnostic_errors
        self._task_lookup = task_lookup
        self._generic: GenericWorkloadTaskRunner | None = None

    @property
    def diagnostic_errors(self) -> tuple[str, ...]:
        return () if self._generic is None else self._generic.diagnostic_errors

    def _run_cognition(self, task: MinecraftTaskSpec, context: ExecutionContext) -> MinecraftTaskRunResult:
        session = getattr(self.environment, "session", None)
        if session is None:
            raise MinecraftWorkloadFailure(
                "cognition",
                "MC_COGNITION_SESSION_MISSING",
                "cognition mode requires an environment session adapter",
                scope=FailureScope.BRANCH,
            )
        from .minecraft_agent import (
            SemPaperCognitionEvidenceAdapter,
            SemMethodAgentMemoryAdapter,
            SemPaperCognitionPlannerAdapter,
        )

        started = time.monotonic()
        progress = (
            self.cognition_checkpoints.progress_for(task.task_id)
            if self.cognition_checkpoints is not None
            else _CognitionProgressCapture()
        )
        restored_checkpoint = (
            self.cognition_checkpoints.checkpoint_for(task.task_id)
            if self.cognition_checkpoints is not None
            else None
        )
        agent_context = replace(
            context,
            task_id=task.task_id,
            decision_cycle_id=f"{task.task_id}:cognition",
        )
        cognition_success = {"kind": task.success.kind, **dict(task.success.params)}
        if task.success.kind == "planner_finish":
            # Planner finish is a generic/non-primary compatibility mode; SEM
            # still requires independent verified action evidence.
            cognition_success = {"kind": "last_action_verified"}
        elif task.success.kind == "blueprint_complete":
            # Platform owns generic cognition termination.  The SEM project
            # evaluates the stronger frozen blueprint contract from grounded
            # action receipts after the loop returns.
            cognition_success = {"kind": "planner_finish"}
        elif task.success.kind in {"away_then_return", "combat_survived"}:
            cognition_success = {"kind": "planner_finish"}
        elif task.success.kind == "inventory_min" and str(task.success.params.get("item", "")).startswith("re:"):
            # Regex inventory predicates are a Paper-1 scientific contract,
            # not part of the frozen upstream Minecraft completion ABI.
            cognition_success = {"kind": "planner_finish"}
        goal = AgentGoal(
            goal_id=task.task_id,
            objective=task.goal,
            context={"success": cognition_success},
            max_steps=task.max_steps,
            max_seconds=task.max_seconds,
        )
        runner = self.cognition_factory.create(
            session=session,
            planner=SemPaperCognitionPlannerAdapter(self.planner, task),
            evidence=SemPaperCognitionEvidenceAdapter(self.evidence),
            progress=progress,
            memory=SemMethodAgentMemoryAdapter(self.method),
            diagnostics=self.diagnostics,
        )
        result = runner.run(
            goal,
            agent_context,
            session_id=f"{context.run_id}:{context.branch_id or 'branch'}:{task.task_id}",
            checkpoint=restored_checkpoint,
        )
        scientific_success = evaluate_cognition_success(task, result)
        failure_reason = (
            ""
            if scientific_success
            else "success_predicate_not_satisfied"
            if result.success
            else (result.failure_code or result.termination.value)
        )
        completion_context = replace(context, task_id=task.task_id, decision_cycle_id=None)
        completion_receipt = self.method.task_completed(
            MethodTaskOutcome(
                task_id=task.task_id, family=task.family, lineage_id=task.lineage_id,
                success=scientific_success, utility=1.0 if scientific_success else 0.0,
                steps=result.steps, failure_reason=failure_reason,
                memory_queries=result.memory_queries,
            ),
            completion_context,
        )
        diagnostics: dict[str, object] = {
            "agent_termination": result.termination.value,
            "agent_failure_code": result.failure_code,
            "agent_plan_calls": result.plan_calls,
            "agent_selected_skills": result.selected_skills,
            "agent_checkpoint_digest": result.checkpoint.digest,
        }
        diagnostics["agent_checkpoint_step"] = result.checkpoint.step
        planner_actions = tuple(
            {
                "action_id": receipt.action_id,
                "action_type": receipt.action_type,
                "skill_id": receipt.skill_id,
                "accepted": receipt.accepted,
                "verified": receipt.verified,
                "effect_certainty": receipt.effect_certainty,
            }
            for receipt in result.action_receipts
        )
        decision_cycles = tuple(
            {"plan_call": index, "skill_id": skill_id}
            for index, skill_id in enumerate(result.selected_skills, start=1)
        )
        return MinecraftTaskRunResult(
            task_id=task.task_id,
            family=task.family,
            lineage_id=task.lineage_id,
            success=scientific_success,
            utility=1.0 if scientific_success else 0.0,
            steps=result.steps,
            duration_s=time.monotonic() - started,
            failure_reason=failure_reason,
            memory_queries=result.memory_queries,
            planner_actions=planner_actions,
            decision_cycles=decision_cycles,
            completion_receipt=completion_receipt,
            diagnostics=diagnostics,
        )

    def run(self, task: MinecraftTaskSpec, context: ExecutionContext) -> MinecraftTaskRunResult:
        if self.cognition_factory is not None:
            return self._run_cognition(task, context)
        self._task_lookup[task.task_id] = task
        boundary = (
            _MinecraftBoundaryAdapter(self.environment)
            if isinstance(self.environment, MinecraftWorkloadBoundaryPort)
            else None
        )
        self._generic = GenericWorkloadTaskRunner(
            environment=_MinecraftGenericEnvironment(self.environment),
            method=self.method,
            evidence=_MinecraftEvidenceAdapter(self.evidence),
            planner=_MinecraftPlannerAdapter(self.planner, self._task_lookup),
            state=_MinecraftStateProjection(),
            completion=_MinecraftCompletionAdapter(self._task_lookup),
            failure_policy=_MinecraftFailurePolicy(),
            diagnostics=self.diagnostics,
            boundary=boundary,
            action_adapter=_MinecraftActionAdapter(),
            max_diagnostic_errors=self.max_diagnostic_errors,
            event_prefix="MC",
            metric_prefix="minecraft.task",
        )
        try:
            result = self._generic.run(task.as_experiment_task(), context)
        except WorkloadTaskRunError as exc:
            code = exc.code.replace("WORKLOAD_", "MC_WORKLOAD_", 1)
            descriptor = describe_exception(exc)
            raise MinecraftWorkloadFailure(
                exc.phase,
                code,
                f"{descriptor.error_type}:{descriptor.safe_message} [{descriptor.error_digest[:12]}]",
                scope=exc.scope,
            ) from exc
        failure_reason = (
            "success_predicate_not_satisfied"
            if result.failure_reason == "completion_predicate_not_satisfied"
            else result.failure_reason
        )
        return MinecraftTaskRunResult(
            task_id=result.task_id,
            family=result.family,
            lineage_id=result.lineage_id,
            success=result.success,
            utility=result.utility,
            steps=result.steps,
            duration_s=result.duration_s,
            failure_reason=failure_reason,
            memory_queries=result.memory_queries,
            planner_actions=result.planner_actions,
            decision_cycles=result.decision_cycles,
            completion_receipt=result.completion_receipt,
            diagnostics=result.diagnostics,
        )


__all__ = [
    "MinecraftEnvironmentActionResult",
    "MinecraftEnvironmentObservation",
    "MinecraftEvidencePort",
    "MinecraftPlannerDecision",
    "MinecraftPlannerPort",
    "MinecraftSuccessSpec",
    "MinecraftTaskRunResult",
    "MinecraftCognitionCheckpointPort",
    "MinecraftCognitionFactoryPort",
    "MinecraftCognitionRunnerPort",
    "MinecraftTaskSpec",
    "PRIMARY_TASK_FAMILIES",
    "PrimaryTaskFamily",
    "MinecraftWorkloadDiagnosticsPort",
    "MinecraftWorkloadBoundaryPort",
    "MinecraftWorkloadEnvironmentPort",
    "MinecraftWorkloadFailure",
    "MinecraftWorkloadRunner",
    "ScriptedMinecraftPlanner",
    "evaluate_success",
    "task_from_mapping",
    "minecraft_task_manifest_digest",
    "validate_task_manifest",
    "validate_primary_task_manifest",
]
