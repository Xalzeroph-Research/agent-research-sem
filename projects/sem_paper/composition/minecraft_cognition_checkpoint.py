from __future__ import annotations

"""Project-owned durable checkpoint component for Minecraft cognition ancestry.

The platform checkpoint coordinator owns atomic workload checkpoint publication.
This component owns only the SEM binding's task-keyed ``AgentLoopCheckpoint``
state so a committed task-boundary cut records the cognition trajectory that
produced it.  Uncommitted in-task progress is intentionally rolled back with the
rest of the workload to the previous committed task boundary.
"""

import json
import threading
from typing import Mapping

from research_platform.participant.agent.api import (
    AgentActionSummary,
    AgentLoopCheckpoint,
    AgentProgressPort,
)
from research_platform.platform.kernel import ExecutionContext, canonical_bytes


_CHECKPOINT_FIELDS = {
    "schema_version",
    "session_id",
    "goal_digest",
    "step",
    "plan_calls",
    "no_progress_steps",
    "same_action_runs",
    "last_observation_digest",
    "action_summaries",
    "last_receipt",
}
_SUMMARY_FIELDS = {
    "action_id",
    "action_type",
    "skill_id",
    "accepted",
    "verified",
    "observation_digest",
    "rationale",
    "payload",
}
_RECEIPT_FIELDS = {
    "action_id",
    "action_type",
    "skill_id",
    "sequence_id",
    "accepted",
    "verified",
    "effect_id",
    "effect_certainty",
}


def _strict_non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"cognition checkpoint {field} must be a non-negative integer")
    return value


def _strict_text(value: object, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(f"cognition checkpoint {field} must be text")
    return value


def _summary_document(summary: AgentActionSummary) -> dict[str, object]:
    return {
        "action_id": summary.action_id,
        "action_type": summary.action_type,
        "skill_id": summary.skill_id,
        "accepted": summary.accepted,
        "verified": summary.verified,
        "observation_digest": summary.observation_digest,
        "rationale": summary.rationale,
        "payload": dict(summary.payload),
    }


def _receipt_document(receipt: object | None) -> dict[str, object] | None:
    if receipt is None:
        return None
    return {
        "action_id": receipt.action_id,
        "action_type": receipt.action_type,
        "skill_id": receipt.skill_id,
        "sequence_id": receipt.sequence_id,
        "accepted": receipt.accepted,
        "verified": receipt.verified,
        "effect_id": receipt.effect_id,
        "effect_certainty": receipt.effect_certainty,
    }


def _checkpoint_document(checkpoint: AgentLoopCheckpoint) -> dict[str, object]:
    return {
        "schema_version": checkpoint.schema_version,
        "session_id": checkpoint.session_id,
        "goal_digest": checkpoint.goal_digest,
        "step": checkpoint.step,
        "plan_calls": checkpoint.plan_calls,
        "no_progress_steps": checkpoint.no_progress_steps,
        "same_action_runs": checkpoint.same_action_runs,
        "last_observation_digest": checkpoint.last_observation_digest,
        "action_summaries": [_summary_document(item) for item in checkpoint.action_summaries],
        "last_receipt": _receipt_document(getattr(checkpoint, "last_receipt", None)),
    }


def _decode_summary(document: object) -> AgentActionSummary:
    if not isinstance(document, Mapping) or set(document) != _SUMMARY_FIELDS:
        raise ValueError("cognition action summary fields are not exact")
    accepted = document["accepted"]
    verified = document["verified"]
    payload = document["payload"]
    if not isinstance(accepted, bool):
        raise ValueError("cognition action summary accepted must be boolean")
    if verified is not None and not isinstance(verified, bool):
        raise ValueError("cognition action summary verified must be boolean or null")
    if not isinstance(payload, Mapping):
        raise ValueError("cognition action summary payload must be a mapping")
    return AgentActionSummary(
        action_id=_strict_text(document["action_id"], "action_id"),
        action_type=_strict_text(document["action_type"], "action_type"),
        skill_id=_strict_text(document["skill_id"], "skill_id"),
        accepted=accepted,
        verified=verified,
        observation_digest=_strict_text(
            document["observation_digest"], "observation_digest", allow_empty=True
        ),
        rationale=_strict_text(document["rationale"], "rationale", allow_empty=True),
        payload=dict(payload),
    )


def _decode_receipt(document: object):
    if document is None:
        return None
    if not isinstance(document, Mapping) or set(document) != _RECEIPT_FIELDS:
        raise ValueError("cognition receipt checkpoint fields are not exact")
    try:
        from research_platform.participant.agent.api import AgentReceiptCheckpoint
    except (ImportError, AttributeError) as exc:
        raise ValueError("platform cognition checkpoint does not support receipt state") from exc
    accepted = document["accepted"]
    verified = document["verified"]
    if not isinstance(accepted, bool) or (verified is not None and not isinstance(verified, bool)):
        raise ValueError("cognition receipt accepted/verified state is invalid")
    effect_id = document["effect_id"]
    if effect_id is not None and not isinstance(effect_id, str):
        raise ValueError("cognition receipt effect_id must be text or null")
    return AgentReceiptCheckpoint(
        action_id=_strict_text(document["action_id"], "receipt.action_id"),
        action_type=_strict_text(document["action_type"], "receipt.action_type"),
        skill_id=_strict_text(document["skill_id"], "receipt.skill_id"),
        sequence_id=_strict_text(document["sequence_id"], "receipt.sequence_id"),
        accepted=accepted, verified=verified, effect_id=effect_id,
        effect_certainty=_strict_text(document["effect_certainty"], "receipt.effect_certainty"),
    )


def _decode_checkpoint(document: object) -> AgentLoopCheckpoint:
    if not isinstance(document, Mapping) or set(document) != _CHECKPOINT_FIELDS:
        raise ValueError("cognition checkpoint fields are not exact")
    raw_summaries = document["action_summaries"]
    if not isinstance(raw_summaries, list):
        raise ValueError("cognition checkpoint action_summaries must be a list")
    kwargs = {
        "schema_version": _strict_text(document["schema_version"], "schema_version"),
        "session_id": _strict_text(document["session_id"], "session_id"),
        "goal_digest": _strict_text(document["goal_digest"], "goal_digest"),
        "step": _strict_non_negative_int(document["step"], "step"),
        "plan_calls": _strict_non_negative_int(document["plan_calls"], "plan_calls"),
        "no_progress_steps": _strict_non_negative_int(document["no_progress_steps"], "no_progress_steps"),
        "same_action_runs": _strict_non_negative_int(document["same_action_runs"], "same_action_runs"),
        "last_observation_digest": _strict_text(document["last_observation_digest"], "last_observation_digest", allow_empty=True),
        "action_summaries": tuple(_decode_summary(item) for item in raw_summaries),
    }
    raw_receipt = document["last_receipt"]
    if "last_receipt" in getattr(AgentLoopCheckpoint, "__dataclass_fields__", {}):
        kwargs["last_receipt"] = _decode_receipt(raw_receipt)
    elif raw_receipt is not None:
        raise ValueError("platform cognition checkpoint does not support persisted receipt state")
    return AgentLoopCheckpoint(**kwargs)


class _TaskCognitionProgress(AgentProgressPort):
    def __init__(self, owner: "MinecraftCognitionCheckpointState", task_id: str) -> None:
        self._owner = owner
        self._task_id = task_id

    def persist(self, checkpoint: AgentLoopCheckpoint, context: ExecutionContext) -> None:
        self._owner.persist_for(self._task_id, checkpoint, context)


class MinecraftCognitionCheckpointState:
    """Single in-binding authority for task-keyed cognition checkpoints."""

    component_id = "participant.agent.cognition"
    codec_id = "sem-paper.minecraft-cognition-checkpoints.json"
    schema_version = "2"
    _DOCUMENT_SCHEMA = "sem-paper.minecraft-cognition-checkpoints.v2"

    def __init__(self) -> None:
        self._checkpoints: dict[str, AgentLoopCheckpoint] = {}
        self._lock = threading.RLock()

    def checkpoint_for(self, task_id: str) -> AgentLoopCheckpoint | None:
        if not task_id.strip():
            raise ValueError("cognition checkpoint task id is required")
        with self._lock:
            return self._checkpoints.get(task_id)

    def progress_for(self, task_id: str) -> AgentProgressPort:
        if not task_id.strip():
            raise ValueError("cognition checkpoint task id is required")
        return _TaskCognitionProgress(self, task_id)

    def persist_for(
        self,
        task_id: str,
        checkpoint: AgentLoopCheckpoint,
        context: ExecutionContext,
    ) -> None:
        if not isinstance(checkpoint, AgentLoopCheckpoint):
            raise TypeError("cognition progress must persist AgentLoopCheckpoint")
        if context.task_id != task_id:
            raise ValueError("cognition checkpoint task identity does not match execution context")
        with self._lock:
            current = self._checkpoints.get(task_id)
            if current is not None:
                if (
                    current.session_id != checkpoint.session_id
                    or current.goal_digest != checkpoint.goal_digest
                ):
                    raise ValueError("cognition checkpoint identity drifted within one task")
                if checkpoint.step < current.step or checkpoint.plan_calls < current.plan_calls:
                    raise ValueError("cognition checkpoint counters cannot regress")
            self._checkpoints[task_id] = checkpoint

    def capture(self) -> bytes:
        with self._lock:
            document = {
                "schema_version": self._DOCUMENT_SCHEMA,
                "checkpoints": [
                    {"task_id": task_id, "checkpoint": _checkpoint_document(checkpoint)}
                    for task_id, checkpoint in sorted(self._checkpoints.items())
                ],
            }
        return canonical_bytes(document)

    def restore(self, payload: bytes) -> None:
        try:
            document = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid cognition checkpoint component JSON") from exc
        if not isinstance(document, Mapping) or set(document) != {"schema_version", "checkpoints"}:
            raise ValueError("cognition checkpoint component fields are not exact")
        if document["schema_version"] != self._DOCUMENT_SCHEMA:
            raise ValueError("unsupported cognition checkpoint component schema")
        rows = document["checkpoints"]
        if not isinstance(rows, list):
            raise ValueError("cognition checkpoint component rows must be a list")
        restored: dict[str, AgentLoopCheckpoint] = {}
        for row in rows:
            if not isinstance(row, Mapping) or set(row) != {"task_id", "checkpoint"}:
                raise ValueError("cognition checkpoint row fields are not exact")
            task_id = _strict_text(row["task_id"], "task_id")
            if task_id in restored:
                raise ValueError("cognition checkpoint task ids must be unique")
            restored[task_id] = _decode_checkpoint(row["checkpoint"])
        with self._lock:
            self._checkpoints = restored


__all__ = ["MinecraftCognitionCheckpointState"]
