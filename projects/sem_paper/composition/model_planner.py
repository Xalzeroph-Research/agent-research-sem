from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from typing import Any, Mapping

from noetrium.contracts import (
    ModelCapabilityRequirement,
    ProjectModelClientPort,
    ProjectModelRequest,
    canonical_digest,
)
from noetrium.contracts.systems.model__request import (
    ExecutionContext,
    ModelRequestRecorderPort,
)

ALLOWED_ACTIONS = frozenset({
    "collect_block", "craft_item", "smelt_item", "place_block",
    "move_away", "goto", "defend_self", "observe_entities", "wait",
})


PLANNER_ROLE = "planner"
PLANNER_PROMPT_GENERATION_ID = "sem-planner"
PLANNER_PROMPT_ID = "minecraft-task-planner"
PLANNER_SYSTEM_INSTRUCTION = (
    "Return only valid JSON. You are a bounded Minecraft action planner. "
    "Never claim task success; the environment verifies it."
)
PLANNER_PROMPT_CONTRACT = {
    "role": PLANNER_ROLE,
    "prompt_generation_id": PLANNER_PROMPT_GENERATION_ID,
    "prompt_id": PLANNER_PROMPT_ID,
    "system_instruction": PLANNER_SYSTEM_INSTRUCTION,
    "output_contract": {"actions": "bounded Minecraft action objects"},
    "allowed_actions": tuple(sorted(ALLOWED_ACTIONS)),
}
PLANNER_PROMPT_DIGEST = canonical_digest(PLANNER_PROMPT_CONTRACT)


def planner_model_requirement() -> ModelCapabilityRequirement:
    return ModelCapabilityRequirement(
        role=PLANNER_ROLE,
        prompt_generation_id=PLANNER_PROMPT_GENERATION_ID,
        prompt_id=PLANNER_PROMPT_ID,
        prompt_digest=PLANNER_PROMPT_DIGEST,
    )


@dataclass(frozen=True, slots=True)
class ModelPlannerConfig:
    max_tokens: int = 1200
    temperature: float = 0.0

    @classmethod
    def from_env(cls) -> "ModelPlannerConfig":
        return cls(
            max_tokens=int(os.environ.get("SEM_MODEL_MAX_TOKENS", "1200")),
            temperature=float(os.environ.get("SEM_MODEL_TEMPERATURE", "0")),
        )


class ModelActionPlanner:
    """SEM-owned planner semantics over one Noetrium-qualified project model client."""

    def __init__(
        self,
        client: ProjectModelClientPort,
        request_recorder: ModelRequestRecorderPort,
        config: ModelPlannerConfig | None = None,
    ) -> None:
        if not isinstance(client, ProjectModelClientPort):
            raise TypeError("SEM model planner requires ProjectModelClientPort")
        if not isinstance(request_recorder, ModelRequestRecorderPort):
            raise TypeError("SEM model planner requires ModelRequestRecorderPort")
        binding = client.binding
        if (
            binding.role != PLANNER_ROLE
            or binding.prompt_generation_id != PLANNER_PROMPT_GENERATION_ID
            or binding.prompt_id != PLANNER_PROMPT_ID
            or binding.prompt_digest != PLANNER_PROMPT_DIGEST
        ):
            raise ValueError("SEM planner client prompt binding drift")
        self.client = client
        self.request_recorder = request_recorder
        self.config = config or ModelPlannerConfig.from_env()
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def plan(
        self,
        *,
        task: Mapping[str, Any],
        memory_context: str,
        snapshot: Mapping[str, Any],
        context: ExecutionContext,
    ) -> tuple[tuple[str, Mapping[str, Any], float], ...]:
        if not isinstance(context, ExecutionContext):
            raise TypeError("SEM planner request requires ExecutionContext")
        self.calls += 1
        prompt_text = self._prompt(task, memory_context, snapshot)
        payload = {
            "model": self.client.binding.model.logical_name,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [
                {"role": "system", "content": PLANNER_SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt_text},
            ],
        }
        envelope = self.request_recorder.record(
            request_id=f"{context.run_id}:sem-planner:{self.calls}",
            context=context,
            role=PLANNER_ROLE,
            model=self.client.binding.model,
            prompt_generation_id=PLANNER_PROMPT_GENERATION_ID,
            prompt_id=PLANNER_PROMPT_ID,
            prompt_digest=PLANNER_PROMPT_DIGEST,
            request_body=payload,
            compiled_prompt_text=prompt_text,
        )
        response = self.client.complete(
            ProjectModelRequest(
                self.client.binding.requirement_digest,
                envelope,
                payload,
            )
        )
        self.prompt_tokens += int(response.input_tokens or 0)
        self.completion_tokens += int(response.output_tokens or 0)
        try:
            return self._parse_actions(response.text, int(task.get("max_steps", 12)))
        except ValueError as exc:
            excerpt = str(response.text).replace("\n", " ")[-1200:]
            raise ValueError(f"{exc}; raw_model_output={excerpt}") from exc

    @staticmethod
    def _prompt(task: Mapping[str, Any], memory_context: str, snapshot: Mapping[str, Any]) -> str:
        allowed = ", ".join(sorted(ALLOWED_ACTIONS))
        task_view = {key: value for key, value in task.items() if key != "action_plan"}
        return (
            "Plan the next bounded action sequence for this Minecraft task. "
            "Use only the allowed action types and at most max_steps actions. "
            "Arguments must be concrete JSON values. Prefer short sequences and "
            "respect the observed inventory; historical memory is advisory and "
            "may be stale. Output exactly {\"actions\":[...]}.\n\n"
            f"Task: {json.dumps(task_view, sort_keys=True, ensure_ascii=False)}\n"
            f"Current snapshot: {json.dumps(dict(snapshot), sort_keys=True, ensure_ascii=False)}\n"
            f"Historical memory: {memory_context[:12000]}\n"
            f"Allowed action types: {allowed}"
        )

    @staticmethod
    def _parse_actions(content: str, max_steps: int) -> tuple[tuple[str, Mapping[str, Any], float], ...]:
        text = re.sub(r"<think>.*?</think>", "", str(content), flags=re.DOTALL).strip()
        text = re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$", "", text, flags=re.IGNORECASE).strip()
        start = text.find("{")
        if start < 0:
            raise ValueError("model planner did not return a JSON object")
        try:
            document, _ = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError as exc:
            raise ValueError("model planner did not return a valid JSON object") from exc
        rows = document.get("actions") if isinstance(document, Mapping) else None
        if not isinstance(rows, list):
            raise ValueError("model planner response must contain an actions array")
        if len(rows) > max(1, max_steps):
            raise ValueError("model planner exceeded task action budget")
        plan: list[tuple[str, Mapping[str, Any], float]] = []
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError("model planner action must be an object")
            action_value = row.get("action_type", row.get("type", row.get("action", "")))
            nested_action = dict(action_value) if isinstance(action_value, Mapping) else None
            if nested_action is not None:
                action_type = str(
                    nested_action.get(
                        "action_type",
                        nested_action.get("type", nested_action.get("tool", nested_action.get("action", "")))
                    )
                ).strip()
            else:
                action_type = str(action_value).strip()
            if action_type not in ALLOWED_ACTIONS and action_type in {"position", "move"}:
                if any(key in row for key in ("target", "target_position", "position")):
                    action_type = "goto"
            if action_type not in ALLOWED_ACTIONS:
                raise ValueError(f"model planner emitted unsupported action: {action_type}")
            arguments = row.get("arguments")
            if arguments is None and nested_action is not None:
                arguments = {
                    key: value for key, value in nested_action.items()
                    if key not in {"action_type", "type", "tool", "reason", "timeout_s"}
                }
            if arguments is None:
                arguments = {
                    key: value for key, value in row.items()
                    if key not in {"action_type", "type", "action", "reason", "timeout_s"}
                }
                if "target_position" in arguments and "position" not in arguments:
                    arguments["position"] = arguments.pop("target_position")
                if action_type == "goto" and "target" in arguments and "position" not in arguments:
                    arguments["position"] = arguments.pop("target")
                if "block_type" in arguments and "block" not in arguments:
                    arguments["block"] = arguments.pop("block_type")
                if action_type == "collect_block" and "count" not in arguments:
                    arguments["count"] = 1
            if isinstance(arguments, Mapping):
                arguments = dict(arguments)
                if "target_position" in arguments and "position" not in arguments:
                    arguments["position"] = arguments.pop("target_position")
                if action_type == "goto" and "target" in arguments and "position" not in arguments:
                    arguments["position"] = arguments.pop("target")
                if "block_type" in arguments and "block" not in arguments:
                    arguments["block"] = arguments.pop("block_type")
                if action_type == "collect_block" and "count" not in arguments:
                    arguments["count"] = 1
            if not isinstance(arguments, Mapping):
                raise ValueError("model planner action arguments must be an object")
            timeout_s = float(row.get("timeout_s", 90.0))
            if timeout_s <= 0 or timeout_s > 600:
                raise ValueError("model planner action timeout is out of range")
            plan.append((action_type, dict(arguments), timeout_s))
        return tuple(plan)


__all__ = [
    "ALLOWED_ACTIONS",
    "ModelActionPlanner",
    "ModelPlannerConfig",
    "PLANNER_PROMPT_DIGEST",
    "PLANNER_PROMPT_GENERATION_ID",
    "PLANNER_PROMPT_ID",
    "PLANNER_ROLE",
    "planner_model_requirement",
]
