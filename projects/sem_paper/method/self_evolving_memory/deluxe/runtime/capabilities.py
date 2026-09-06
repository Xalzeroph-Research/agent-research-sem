from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
import hashlib
import math
import re
from typing import Mapping

from ..api import (
    CapabilityCard,
    CapabilityLifecycle,
    CapabilityLifecycleConfig,
    CapabilityState,
    DeluxeArchitectureSnapshot,
)
from research_platform.platform.kernel import JsonObject


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def _tokens(text: str) -> set[str]:
    return {match.group(0).casefold() for match in _TOKEN_RE.finditer(text)}


@dataclass(slots=True)
class CapabilityRegistry:
    """Derived capability view generated from a pinned method architecture."""

    config: CapabilityLifecycleConfig = field(default_factory=CapabilityLifecycleConfig)
    cards: dict[str, CapabilityCard] = field(default_factory=dict)
    lifecycle: dict[str, CapabilityLifecycle] = field(default_factory=dict)
    query_clock: int = 0
    architecture_generation: str | None = None
    architecture_digest: str | None = None

    @staticmethod
    def capability_id(node_id: str) -> str:
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("capability provider node id must be a non-empty string")
        return "cap_" + hashlib.sha256(node_id.encode("utf-8")).hexdigest()[:12]

    def sync_architecture(self, architecture: DeluxeArchitectureSnapshot) -> None:
        if not isinstance(architecture, DeluxeArchitectureSnapshot):
            raise ValueError("capability registry requires a typed architecture snapshot")
        current_nodes = {node.node_id for node in architecture.nodes}
        for node in architecture.nodes:
            capability_id = self.capability_id(node.node_id)
            prior = self.cards.get(capability_id)
            if prior is None:
                self.cards[capability_id] = CapabilityCard(
                    capability_id=capability_id,
                    provider_node_id=node.node_id,
                    purpose=node.purpose,
                    access=tuple(sorted(node.access)),
                    output_types=tuple(sorted(node.output_types)),
                    scope=node.scope,
                    generation_created=architecture.generation,
                )
                is_new_generation = architecture.generation_number > 0
                self.lifecycle[capability_id] = CapabilityLifecycle(
                    state=CapabilityState.PROBATION if is_new_generation else CapabilityState.ACTIVE,
                    probation_queries_remaining=self.config.probation_queries if is_new_generation else 0,
                    lease_queries_remaining=self.config.lease_queries,
                )
            else:
                self.cards[capability_id] = CapabilityCard(
                    capability_id=capability_id,
                    provider_node_id=node.node_id,
                    purpose=node.purpose,
                    access=tuple(sorted(node.access)),
                    output_types=tuple(sorted(node.output_types)),
                    scope=node.scope,
                    generation_created=prior.generation_created,
                )

        for capability_id, card in tuple(self.cards.items()):
            if card.provider_node_id not in current_nodes:
                self.cards.pop(capability_id, None)
                self.lifecycle.pop(capability_id, None)
        self.architecture_generation = architecture.generation
        self.architecture_digest = architecture.digest

    def tick_query(self) -> None:
        if isinstance(self.query_clock, bool) or not isinstance(self.query_clock, int) or self.query_clock < 0:
            raise ValueError("capability registry query_clock must be a non-negative integer")
        self.query_clock += 1
        cfg = self.config
        for capability_id, lifecycle in self.lifecycle.items():
            lifecycle.validate()
            lifecycle.age_queries += 1
            if lifecycle.probation_queries_remaining > 0:
                lifecycle.probation_queries_remaining -= 1
                if lifecycle.probation_queries_remaining == 0 and lifecycle.state is CapabilityState.PROBATION:
                    lifecycle.state = (
                        CapabilityState.ACTIVE
                        if lifecycle.selected_queries >= cfg.min_probation_selections
                        and lifecycle.usefulness_rate() >= cfg.min_probation_usefulness
                        else CapabilityState.DORMANT
                    )
            if lifecycle.lease_queries_remaining > 0:
                lifecycle.lease_queries_remaining -= 1
            idle = (
                self.query_clock - lifecycle.last_selected_query
                if lifecycle.last_selected_query >= 0
                else lifecycle.age_queries
            )
            if lifecycle.state is CapabilityState.ACTIVE and idle >= cfg.dormant_after_queries:
                lifecycle.state = CapabilityState.DORMANT
            if lifecycle.state is CapabilityState.DORMANT and idle >= cfg.retire_after_dormant_queries:
                lifecycle.state = CapabilityState.RETIRE_CANDIDATE

    def discover(
        self,
        intent: str,
        *,
        required_access: str | None = None,
        include_dormant: bool = False,
    ) -> list[tuple[float, CapabilityCard]]:
        if not isinstance(intent, str):
            raise ValueError("capability discovery intent must be a string")
        if required_access is not None and (not isinstance(required_access, str) or not required_access.strip()):
            raise ValueError("required_access must be a non-empty string when present")
        if not isinstance(include_dormant, bool):
            raise ValueError("include_dormant must be boolean")
        intent_tokens = _tokens(intent)
        ranked: list[tuple[float, CapabilityCard]] = []
        for capability_id, card in self.cards.items():
            lifecycle = self.lifecycle[capability_id]
            if lifecycle.state is CapabilityState.RETIRE_CANDIDATE:
                continue
            if lifecycle.state is CapabilityState.DORMANT and not include_dormant:
                continue
            if required_access is not None and required_access not in card.access:
                continue
            card_tokens = _tokens(card.semantic_card)
            lexical = len(intent_tokens & card_tokens) / max(1, len(intent_tokens))
            lifecycle_bonus = (
                0.08
                if lifecycle.state is CapabilityState.ACTIVE
                else -0.03
                if lifecycle.state is CapabilityState.PROBATION
                else -0.10
            )
            utility_bonus = 0.10 * max(-1.0, min(1.0, lifecycle.utility_ema))
            ranked.append((lexical + lifecycle_bonus + utility_bonus, card))
        ranked.sort(key=lambda row: (-row[0], row[1].capability_id))
        return ranked

    def observe_selection(
        self,
        capability_ids: Iterable[str],
        *,
        useful_provider_ids: Iterable[str] = (),
        utility: float = 0.0,
    ) -> None:
        if isinstance(capability_ids, (str, bytes)) or isinstance(useful_provider_ids, (str, bytes)):
            raise ValueError("capability observations require iterables of identifiers, not scalar text")
        selected = tuple(capability_ids)
        useful_rows = tuple(useful_provider_ids)
        if any(not isinstance(value, str) or not value.strip() for value in (*selected, *useful_rows)):
            raise ValueError("capability observation identifiers must be non-empty strings")
        if len(selected) != len(set(selected)) or len(useful_rows) != len(set(useful_rows)):
            raise ValueError("capability observation identifiers must be unique")
        unknown = [capability_id for capability_id in selected if capability_id not in self.cards or capability_id not in self.lifecycle]
        if unknown:
            raise ValueError(f"unknown capability observation ids: {sorted(unknown)}")
        selected_provider_ids = {self.cards[capability_id].provider_node_id for capability_id in selected}
        useful = set(useful_rows)
        if not useful <= selected_provider_ids:
            raise ValueError("useful providers must be a subset of selected capability providers")
        if isinstance(utility, bool) or not isinstance(utility, (int, float)):
            raise ValueError("capability observation utility must be numeric")
        try:
            numeric_utility = float(utility)
        except OverflowError as exc:
            raise ValueError("capability observation utility must be finite") from exc
        if not math.isfinite(numeric_utility):
            raise ValueError("capability observation utility must be finite")
        for capability_id in selected:
            lifecycle = self.lifecycle[capability_id]
            card = self.cards[capability_id]
            lifecycle.validate()
            lifecycle.selected_queries += 1
            lifecycle.last_selected_query = self.query_clock
            if card.provider_node_id in useful:
                lifecycle.useful_queries += 1
            lifecycle.utility_ema = 0.8 * lifecycle.utility_ema + 0.2 * numeric_utility
            if lifecycle.state is CapabilityState.DORMANT:
                lifecycle.state = CapabilityState.PROBATION
                lifecycle.probation_queries_remaining = max(2, self.config.probation_queries // 2)

    def capability_for_node(self, node_id: str) -> str | None:
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("capability lookup node_id must be a non-empty string")
        return next(
            (capability_id for capability_id, card in self.cards.items() if card.provider_node_id == node_id),
            None,
        )

    def retire_candidate_nodes(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                self.cards[capability_id].provider_node_id
                for capability_id, lifecycle in self.lifecycle.items()
                if lifecycle.state is CapabilityState.RETIRE_CANDIDATE
            )
        )

    def disclosed_cards(self, intent: str, *, limit: int = 6) -> tuple[CapabilityCard, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("capability disclosure limit must be a positive integer")
        return tuple(card for _, card in self.discover(intent)[:limit])

    def snapshot(self) -> JsonObject:
        return {
            "architecture_generation": self.architecture_generation,
            "architecture_digest": self.architecture_digest,
            "query_clock": self.query_clock,
            "capabilities": [
                {
                    "capability_id": capability_id,
                    "provider_node_id": self.cards[capability_id].provider_node_id,
                    "state": self.lifecycle[capability_id].state.value,
                    "selected_queries": self.lifecycle[capability_id].selected_queries,
                    "useful_queries": self.lifecycle[capability_id].useful_queries,
                    "utility_ema": self.lifecycle[capability_id].utility_ema,
                }
                for capability_id in sorted(self.cards)
            ],
        }


__all__ = ["CapabilityRegistry"]
