from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from research_platform.platform.kernel import JsonObject, JsonValue, canonical_digest


SCHEMA_VERSION = "sem-paper.minecraft-planner-execution.v1"
MAX_RECENT_ACTIONS = 12
MAX_REPEATED_ACTIONS = 6


@dataclass(frozen=True, slots=True)
class RepeatedUnverifiedAction:
    action_type: str
    arguments: JsonObject
    attempts: int

    def as_payload(self) -> JsonObject:
        return {
            "action_type": self.action_type,
            "arguments": dict(self.arguments),
            "attempts": self.attempts,
        }


@dataclass(frozen=True, slots=True)
class SemPaperMinecraftPlannerExecutionSemantics:
    repeated_unverified_actions: tuple[RepeatedUnverifiedAction, ...]

    @classmethod
    def from_prior_actions(
        cls,
        prior_actions: tuple[Mapping[str, JsonValue], ...],
    ) -> "SemPaperMinecraftPlannerExecutionSemantics":
        counts: dict[str, tuple[str, JsonObject, int]] = {}
        for row in prior_actions[-MAX_RECENT_ACTIONS:]:
            if row.get("verified") is True:
                continue
            action_type = str(row.get("action_type", "")).strip()
            raw_arguments = row.get("payload", {})
            if not action_type or not isinstance(raw_arguments, Mapping):
                continue
            arguments = dict(raw_arguments)
            key = canonical_digest({"action_type": action_type, "arguments": arguments})
            _, _, count = counts.get(key, (action_type, arguments, 0))
            counts[key] = (action_type, arguments, count + 1)
        repeated = tuple(
            RepeatedUnverifiedAction(action_type, arguments, count)
            for action_type, arguments, count in counts.values()
            if count >= 2
        )[:MAX_REPEATED_ACTIONS]
        return cls(repeated)

    def as_payload(self) -> JsonObject:
        return {
            "schema_version": SCHEMA_VERSION,
            "rules": {
                "craft_item": (
                    "Direct craft only: use currently available ingredients and workstation context; "
                    "the tool does not recursively gather or craft missing prerequisites."
                ),
                "verification": (
                    "Rejected, partial, unknown, or otherwise unverified action outcomes are not progress "
                    "and do not satisfy task completion."
                ),
                "retry": (
                    "Do not repeat the same unverified action with identical arguments until verified "
                    "state evidence shows that relevant preconditions changed."
                ),
            },
            "repeated_unverified_actions": [row.as_payload() for row in self.repeated_unverified_actions],
        }


__all__ = ["SCHEMA_VERSION", "SemPaperMinecraftPlannerExecutionSemantics"]
