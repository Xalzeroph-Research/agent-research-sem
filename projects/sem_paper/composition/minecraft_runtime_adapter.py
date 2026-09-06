from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from research_platform.environment.api import ActionRequest, ActionResult, EnvironmentSession, Observation
from research_platform.platform.kernel import ExecutionContext, JsonValue

from .minecraft_workload import (
    MinecraftEnvironmentActionResult,
    MinecraftEnvironmentObservation,
    MinecraftWorkloadEnvironmentPort,
)


class MinecraftWorkloadEnvironmentAdapterError(RuntimeError):
    """The generic environment observation cannot satisfy the Paper workload ABI."""


class _EnvironmentSession(EnvironmentSession, Protocol):
    """Local project seam; the platform Environment ABI is bound at composition."""

    def observe(self, context: ExecutionContext) -> Observation: ...

    def act(self, request: ActionRequest) -> ActionResult: ...

    def begin_task(self, metadata: Mapping[str, JsonValue], context: ExecutionContext) -> Observation | None: ...

    def end_task(self, metadata: Mapping[str, JsonValue], context: ExecutionContext) -> Observation | None: ...


class MinecraftWorkloadEnvironmentAdapter(MinecraftWorkloadEnvironmentPort):
    """Translate the generic environment ABI into the Paper workload seam."""

    def __init__(self, session: _EnvironmentSession) -> None:
        self.session = session

    @staticmethod
    def _observation(value: object) -> MinecraftEnvironmentObservation:
        observation_id = str(getattr(value, "observation_id", ""))
        payload = getattr(value, "payload", None)
        if not observation_id.strip() or not isinstance(payload, Mapping):
            raise MinecraftWorkloadEnvironmentAdapterError(
                "Minecraft environment observation does not satisfy the workload shape"
            )
        if "state" not in payload:
            raise MinecraftWorkloadEnvironmentAdapterError(
                "Minecraft environment observation is missing state"
            )
        state = payload["state"]
        if not isinstance(state, Mapping):
            raise MinecraftWorkloadEnvironmentAdapterError(
                "Minecraft environment observation state must be a mapping"
            )
        return MinecraftEnvironmentObservation(observation_id, dict(state), payload)

    def observe(self, context: ExecutionContext) -> MinecraftEnvironmentObservation:
        try:
            return self._observation(self.session.observe(context))
        except MinecraftWorkloadEnvironmentAdapterError:
            raise
        except Exception as exc:
            raise MinecraftWorkloadEnvironmentAdapterError(
                f"Minecraft workload observe adaptation failed: {type(exc).__name__}"
            ) from exc

    def begin_task(self, metadata: Mapping[str, JsonValue], context: ExecutionContext) -> MinecraftEnvironmentObservation | None:
        try:
            value = self.session.begin_task(dict(metadata), context)
            return None if value is None else self._observation(value)
        except MinecraftWorkloadEnvironmentAdapterError:
            raise
        except Exception as exc:
            raise MinecraftWorkloadEnvironmentAdapterError(
                f"Minecraft workload task-begin adaptation failed: {type(exc).__name__}"
            ) from exc

    def end_task(self, metadata: Mapping[str, JsonValue], context: ExecutionContext) -> MinecraftEnvironmentObservation | None:
        try:
            value = self.session.end_task(dict(metadata), context)
            return None if value is None else self._observation(value)
        except MinecraftWorkloadEnvironmentAdapterError:
            raise
        except Exception as exc:
            raise MinecraftWorkloadEnvironmentAdapterError(
                f"Minecraft workload task-end adaptation failed: {type(exc).__name__}"
            ) from exc

    def act(
        self,
        action_id: str,
        action_type: str,
        payload: Mapping[str, JsonValue],
        context: ExecutionContext,
    ) -> MinecraftEnvironmentActionResult:
        try:
            result = self.session.act(ActionRequest(action_id, action_type, dict(payload), context))
            observation = None if result.observation is None else self._observation(result.observation)
            verified_value = result.diagnostics.get("verified")
            verified = verified_value if isinstance(verified_value, bool) else None
            return MinecraftEnvironmentActionResult(
                accepted=bool(result.accepted),
                verified=verified,
                observation=observation,
                payload=result.diagnostics,
                diagnostics=dict(result.diagnostics),
            )
        except MinecraftWorkloadEnvironmentAdapterError:
            raise
        except Exception as exc:
            raise MinecraftWorkloadEnvironmentAdapterError(
                f"Minecraft workload action adaptation failed: {type(exc).__name__}"
            ) from exc

    def checkpoint(self) -> bytes:
        return self.session.checkpoint()

    def restore(self, payload: bytes) -> None:
        self.session.restore(payload)


__all__ = [
    "MinecraftWorkloadEnvironmentAdapter",
    "MinecraftWorkloadEnvironmentAdapterError",
]
