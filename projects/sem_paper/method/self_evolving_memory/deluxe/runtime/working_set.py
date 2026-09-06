from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Mapping, Sequence

from ..api import (
    CapabilityCard,
    WorkingSet,
    WorkingSetEntry,
    WorkingSetPolicyConfig,
)
from .capabilities import CapabilityRegistry
from research_platform.platform.kernel import JsonObject


@dataclass(slots=True)
class ArchitectureOpenWorkingSetPolicy:
    """Select from capabilities derived from the current architecture."""

    registry: CapabilityRegistry
    config: WorkingSetPolicyConfig = field(default_factory=WorkingSetPolicyConfig)
    provider_utility: dict[str, float] = field(default_factory=dict)
    provider_reliability: dict[str, float] = field(default_factory=dict)
    provider_cost: dict[str, float] = field(default_factory=dict)

    def select(
        self,
        ranked_capabilities: Sequence[tuple[float, CapabilityCard]],
        *,
        budget_nodes: int,
        exploration_slots: int = 0,
    ) -> WorkingSet:
        if isinstance(budget_nodes, bool) or not isinstance(budget_nodes, int) or budget_nodes <= 0:
            raise ValueError("Deluxe working-set budget_nodes must be a positive integer")
        if isinstance(exploration_slots, bool) or not isinstance(exploration_slots, int) or not 0 <= exploration_slots <= budget_nodes:
            raise ValueError("Deluxe working-set exploration_slots is invalid")
        scored: list[tuple[float, CapabilityCard]] = []
        cfg = self.config
        seen_capabilities: set[str] = set()
        for row in ranked_capabilities:
            if not isinstance(row, tuple) or len(row) != 2:
                raise ValueError("ranked capability entries must be (score, CapabilityCard) pairs")
            relevance, card = row
            if not isinstance(card, CapabilityCard):
                raise ValueError("ranked capability entries must contain typed CapabilityCard values")
            if card.capability_id in seen_capabilities:
                raise ValueError("ranked capabilities must not contain duplicate capability ids")
            seen_capabilities.add(card.capability_id)
            if isinstance(relevance, bool) or not isinstance(relevance, (int, float)):
                raise ValueError("ranked capability relevance must be numeric")
            try:
                relevance = float(relevance)
            except OverflowError as exc:
                raise ValueError("ranked capability relevance must be finite") from exc
            if not math.isfinite(relevance):
                raise ValueError("ranked capability relevance must be finite")
            utility = self.provider_utility.get(card.provider_node_id, 0.0)
            reliability = self.provider_reliability.get(card.provider_node_id, 0.5)
            cost = self.provider_cost.get(card.provider_node_id, 0.0)
            normalized_state: list[float] = []
            for label, value in (("utility", utility), ("reliability", reliability), ("cost", cost)):
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"Deluxe working-set provider {label} state must be numeric")
                try:
                    numeric = float(value)
                except OverflowError as exc:
                    raise ValueError(f"Deluxe working-set provider {label} state must be finite") from exc
                if not math.isfinite(numeric):
                    raise ValueError(f"Deluxe working-set provider {label} state must be finite")
                normalized_state.append(numeric)
            utility, reliability, cost = normalized_state
            if not 0.0 <= reliability <= 1.0 or cost < 0.0:
                raise ValueError("Deluxe working-set provider reliability/cost state is out of range")
            score = (
                cfg.relevance_weight * relevance
                + cfg.utility_weight * utility
                + cfg.reliability_weight * reliability
                - cfg.cost_weight * cost
            )
            scored.append((score, card))
        scored.sort(key=lambda row: (-row[0], row[1].capability_id))
        exploit_count = max(1, budget_nodes - exploration_slots)
        chosen = [
            WorkingSetEntry(card.capability_id, card.provider_node_id, score, False)
            for score, card in scored[:exploit_count]
        ]
        if exploration_slots:
            chosen_ids = {entry.capability_id for entry in chosen}
            unexplored = [
                (score, card)
                for score, card in scored
                if card.capability_id not in chosen_ids
                and self.registry.lifecycle[card.capability_id].selected_queries == 0
            ]
            chosen.extend(
                WorkingSetEntry(card.capability_id, card.provider_node_id, score + cfg.exploration_bonus, True)
                for score, card in unexplored[:exploration_slots]
            )
        return WorkingSet(tuple(chosen[:budget_nodes]), budget_nodes)

    def observe(self, node_id: str, *, utility: float, success: bool, cost: float, alpha: float = 0.2) -> None:
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("Deluxe working-set observation node_id must be a non-empty string")
        if not isinstance(success, bool):
            raise ValueError("Deluxe working-set observation success must be boolean")
        numeric: list[float] = []
        for label, raw in (("utility", utility), ("cost", cost), ("alpha", alpha)):
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValueError(f"Deluxe working-set observation {label} must be numeric")
            try:
                converted = float(raw)
            except OverflowError as exc:
                raise ValueError(f"Deluxe working-set observation {label} must be finite") from exc
            if not math.isfinite(converted):
                raise ValueError(f"Deluxe working-set observation {label} must be finite")
            numeric.append(converted)
        utility, cost, alpha = numeric
        if cost < 0.0 or not 0.0 < alpha <= 1.0:
            raise ValueError("Deluxe working-set observation is out of range")
        prior_values = (
            ("utility", self.provider_utility.get(node_id, utility), None),
            ("reliability", self.provider_reliability.get(node_id, 1.0 if success else 0.0), (0.0, 1.0)),
            ("cost", self.provider_cost.get(node_id, cost), (0.0, None)),
        )
        prior: dict[str, float] = {}
        for label, raw, bounds in prior_values:
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValueError(f"Deluxe prior provider {label} state must be numeric")
            try:
                converted = float(raw)
            except OverflowError as exc:
                raise ValueError(f"Deluxe prior provider {label} state must be finite") from exc
            if not math.isfinite(converted):
                raise ValueError(f"Deluxe prior provider {label} state must be finite")
            if bounds is not None:
                lower, upper = bounds
                if converted < lower or (upper is not None and converted > upper):
                    raise ValueError(f"Deluxe prior provider {label} state is out of range")
            prior[label] = converted
        self.provider_utility[node_id] = (1.0 - alpha) * prior["utility"] + alpha * utility
        self.provider_reliability[node_id] = (
            (1.0 - alpha) * prior["reliability"] + alpha * (1.0 if success else 0.0)
        )
        self.provider_cost[node_id] = (1.0 - alpha) * prior["cost"] + alpha * cost

    def snapshot(self) -> JsonObject:
        return {
            "provider_utility": dict(sorted(self.provider_utility.items())),
            "provider_reliability": dict(sorted(self.provider_reliability.items())),
            "provider_cost": dict(sorted(self.provider_cost.items())),
        }


__all__ = ["ArchitectureOpenWorkingSetPolicy"]
