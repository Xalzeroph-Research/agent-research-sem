from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable, Mapping

from research_platform.environment.minecraft.api import (
    MINECRAFT_ACTION_TYPES,
    minecraft_action_catalog,
    validate_minecraft_action,
)
from research_platform.model.request.prompt.api import (
    PromptBodyContext,
    PromptDynamicBlock,
    PromptRequestBindingPort,
    PromptRequestBodyBuilder,
)
from research_platform.model.serving.endpoint import (
    ModelEndpointPort,
    ModelEndpointRequest,
    ModelEndpointResponse,
)
from research_platform.platform.kernel import ExecutionContext, ImmutableModelIdentity, JsonObject, JsonValue, canonical_digest
from projects.sem_paper.method.self_evolving_memory.evolution import BranchRole, CandidateArchitecture

from .minecraft_planner_execution import SemPaperMinecraftPlannerExecutionSemantics
from .minecraft_planner_state import SemPaperMinecraftPlannerStateProjection
from .minecraft_workload import MinecraftPlannerDecision, MinecraftPlannerPort, MinecraftTaskSpec


class SemPaperModelPlannerError(RuntimeError):
    """A model-backed Paper planner failed a typed request/response phase."""

    def __init__(self, message: str, *, phase: str, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.phase = phase
        self.cause = cause


@dataclass(frozen=True, slots=True)
class SemPaperModelPlannerBinding:
    """All immutable identities required by one qualified planner binding."""

    prompt_requests: PromptRequestBindingPort
    body_builder: PromptRequestBodyBuilder
    model: ImmutableModelIdentity
    deployment_id: str
    deployment_generation: str
    context_length: int
    endpoint: ModelEndpointPort
    request_id_factory: Callable[[ExecutionContext, MinecraftTaskSpec, int, BranchRole, CandidateArchitecture | None], str] | None = None

    def __post_init__(self) -> None:
        if not self.deployment_id.strip() or len(self.deployment_generation) != 64:
            raise ValueError("Paper model planner requires exact deployment identity")
        if self.context_length <= 0:
            raise ValueError("Paper model planner context_length must be positive")


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _block(kind: str, value: object, sequence: int) -> PromptDynamicBlock:
    content = _json_text(value) if not isinstance(value, str) else value
    return PromptDynamicBlock(kind, content, canonical_digest(value), sequence)


class SemPaperModelPlanner(MinecraftPlannerPort):
    """Strict model-backed planner over the frozen prompt and endpoint seams."""

    def __init__(
        self,
        *,
        binding: SemPaperModelPlannerBinding,
        role: BranchRole,
        candidate: CandidateArchitecture | None,
    ) -> None:
        self._binding = binding
        self._role = role
        self._candidate = candidate

    def _request_id(self, context: ExecutionContext, task: MinecraftTaskSpec, step: int) -> str:
        if self._binding.request_id_factory is not None:
            return self._binding.request_id_factory(
                context,
                task,
                step,
                self._role,
                self._candidate,
            )
        return ":".join((
            "sem-paper",
            "planner",
            context.run_id,
            context.branch_id or "no-branch",
            task.task_id,
            context.decision_cycle_id or f"step-{step}",
            self._role.value,
            self._candidate.candidate_id if self._candidate is not None else "fixed",
        ))

    def _source_artifacts(self) -> tuple[str, ...]:
        if self._candidate is None:
            return ("sem-paper:method:fixed",)
        return (
            f"sem-paper:candidate:{self._candidate.candidate_id}",
            f"sem-paper:candidate-spec:{self._candidate.target_spec_digest}",
        )

    def decide(
        self,
        *,
        task: MinecraftTaskSpec,
        context: ExecutionContext,
        state: Mapping[str, JsonValue],
        memory_context: str,
        step: int,
        prior_actions: tuple[Mapping[str, JsonValue], ...],
    ) -> MinecraftPlannerDecision:
        request_id = self._request_id(context, task, step)
        projected_state = SemPaperMinecraftPlannerStateProjection.from_state(state).as_payload()
        execution_semantics = SemPaperMinecraftPlannerExecutionSemantics.from_prior_actions(
            prior_actions
        ).as_payload()
        if len(_json_text(projected_state)) > 16_000:
            raise SemPaperModelPlannerError(
                "Minecraft planner-state projection exceeded its SEM budget",
                phase="state_projection",
            )
        blocks = (
            _block("task", {
                "task_id": task.task_id,
                "family": task.family,
                "goal": task.goal,
                "context": task.context,
                "success": {"kind": task.success.kind, "params": dict(task.success.params)},
                "step": step,
            }, 10),
            _block("verified_state", projected_state, 20),
            _block("tool_catalog", {
                "actions": [
                    contract.as_payload()
                    for contract in minecraft_action_catalog()
                ],
                "completion": "finish only when completion_claim is true",
                "execution_semantics": execution_semantics,
            }, 30),
        )
        if memory_context.strip():
            blocks += (_block("memory_context", memory_context, 40),)
        if prior_actions:
            blocks += (_block("prior_outcome", prior_actions, 50),)

        try:
            bound = self._binding.prompt_requests.build(
                blocks=blocks,
                context_length=self._binding.context_length,
                request_id=request_id,
                context=context,
                model=self._binding.model,
                body_builder=self._binding.body_builder,
                source_artifact_refs=self._source_artifacts(),
                source_state_refs=(
                    f"minecraft:task:{task.task_id}",
                    f"minecraft:observation:{canonical_digest(dict(state))}",
                ),
            )
            response = self._binding.endpoint.complete(ModelEndpointRequest(
                request=bound.request,
                deployment_id=self._binding.deployment_id,
                deployment_generation=self._binding.deployment_generation,
                body=bound.body,
            ))
            self._verify_response(response, request_id)
            payload = self._parse(response.text)
            decision = self._decision(payload)
            return decision
        except BaseException as exc:
            if isinstance(exc, SemPaperModelPlannerError):
                raise
            raise SemPaperModelPlannerError(
                f"Paper model planner failed: {type(exc).__name__}",
                phase="request_or_response",
                cause=exc,
            ) from exc

    @staticmethod
    def body(context: PromptBodyContext) -> JsonObject:
        return {
            # The qualified Qwen serving profile requires a user turn. The compiled
            # prompt already contains the immutable planner instructions and
            # dynamic task/state blocks, so placing it in the user turn keeps
            # the frozen prompt content unchanged while satisfying the model
            # serving ABI.
            "messages": [{"role": "user", "content": context.compiled_text}],
            "model": context.model_id,
            "temperature": context.temperature,
            "top_p": context.top_p,
            "max_tokens": context.max_output_tokens,
            # SEM requires an action JSON, not hidden reasoning that can consume
            # the bounded completion budget before any visible action is emitted.
            # Freeze the Qwen chat-template mode instead of inheriting a mutable
            # serving default; Server1 qualification canaries exercise this exact seam.
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "planner_action_v2", "strict": True,
                    "schema": {
                        "type": "object", "additionalProperties": False,
                        "required": ["action_type", "arguments", "completion_claim"],
                        "properties": {
                            "action_type": {"type": "string"},
                            "arguments": {"type": "object"},
                            "completion_claim": {"type": "boolean"},
                        },
                    },
                },
            },
        }

    def _verify_response(self, response: ModelEndpointResponse, request_id: str) -> None:
        if response.request_id != request_id:
            raise SemPaperModelPlannerError(
                "model endpoint response request identity drift",
                phase="response_identity",
            )
        if response.deployment_id != self._binding.deployment_id:
            raise SemPaperModelPlannerError(
                "model endpoint response deployment identity drift",
                phase="response_identity",
            )
        if response.finish_reason != "stop":
            raise SemPaperModelPlannerError(
                f"model endpoint response did not complete normally: {response.finish_reason}",
                phase="response_completion",
            )

    @staticmethod
    def _parse(text: str) -> dict[str, object]:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SemPaperModelPlannerError("planner response is not strict JSON", phase="parse", cause=exc) from exc
        if not isinstance(payload, dict):
            raise SemPaperModelPlannerError("planner response must be a JSON object", phase="schema")
        expected = {"action_type", "arguments", "completion_claim"}
        if set(payload) != expected:
            raise SemPaperModelPlannerError("planner response fields do not match planner_action_v2", phase="schema")
        if not isinstance(payload["action_type"], str) or not payload["action_type"].strip():
            raise SemPaperModelPlannerError("planner action_type must be non-empty text", phase="schema")
        if not isinstance(payload["arguments"], Mapping):
            raise SemPaperModelPlannerError("planner arguments must be an object", phase="schema")
        if not isinstance(payload["completion_claim"], bool):
            raise SemPaperModelPlannerError("planner completion_claim must be boolean", phase="schema")
        return payload

    @staticmethod
    def _decision(payload: Mapping[str, JsonValue]) -> MinecraftPlannerDecision:
        action_type = str(payload["action_type"])
        completion_claim = bool(payload["completion_claim"])
        arguments = dict(payload["arguments"])
        if action_type == "finish":
            if not completion_claim:
                raise SemPaperModelPlannerError("finish requires completion_claim=true", phase="action_contract")
            return MinecraftPlannerDecision("finish", arguments, "model:completion_claim")
        if completion_claim:
            raise SemPaperModelPlannerError("non-finish action cannot claim completion", phase="action_contract")
        if action_type not in MINECRAFT_ACTION_TYPES:
            raise SemPaperModelPlannerError(f"unsupported Minecraft action: {action_type}", phase="action_contract")
        try:
            normalized = validate_minecraft_action(action_type, arguments)
        except Exception as exc:
            raise SemPaperModelPlannerError(
                f"planner action violates Minecraft action contract: {action_type}",
                phase="action_contract",
                cause=exc,
            ) from exc
        return MinecraftPlannerDecision(action_type, normalized, "model:planner.v6")


class SemPaperModelPlannerFactory:
    """Bind one frozen model/prompt endpoint to both Paper branch roles."""

    def __init__(self, binding: SemPaperModelPlannerBinding) -> None:
        self.binding = binding

    def create(self, *, role: BranchRole, candidate: CandidateArchitecture | None, task: MinecraftTaskSpec, method: object) -> MinecraftPlannerPort:
        del task, method
        if role is BranchRole.CONTROL and candidate is not None:
            raise ValueError("control planner cannot receive a candidate")
        if role is BranchRole.CANDIDATE and candidate is None:
            raise ValueError("candidate planner requires a candidate")
        return SemPaperModelPlanner(binding=self.binding, role=role, candidate=candidate)


__all__ = [
    "SemPaperModelPlanner",
    "SemPaperModelPlannerBinding",
    "SemPaperModelPlannerError",
    "SemPaperModelPlannerFactory",
]
