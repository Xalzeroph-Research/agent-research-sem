from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Mapping

from ..api import BudgetPolicyConfig, QueryBudget
from research_platform.platform.kernel import JsonObject


@dataclass(slots=True)
class FineGrainedBudgetPolicy:
    """Port of the legacy Deluxe allocation policy over current read contracts."""

    config: BudgetPolicyConfig = field(default_factory=BudgetPolicyConfig)
    node_cost_ema: dict[str, float] = field(default_factory=dict)
    capability_cost_ema: dict[str, float] = field(default_factory=dict)

    def allocate(
        self,
        *,
        requested_nodes: int,
        requested_records: int,
        node_count: int,
        unresolved_rate: float = 0.0,
        cost_pressure: float = 0.0,
    ) -> QueryBudget:
        for label, value in (("requested_nodes", requested_nodes), ("requested_records", requested_records), ("node_count", node_count)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"Deluxe budget {label} must be a non-negative integer")
        normalized_rates: list[float] = []
        for label, value in (("unresolved_rate", unresolved_rate), ("cost_pressure", cost_pressure)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"Deluxe budget {label} must be numeric")
            try:
                numeric = float(value)
            except OverflowError as exc:
                raise ValueError(f"Deluxe budget {label} must be finite and non-negative") from exc
            if not math.isfinite(numeric) or numeric < 0.0:
                raise ValueError(f"Deluxe budget {label} must be finite and non-negative")
            normalized_rates.append(numeric)
        unresolved_rate, cost_pressure = normalized_rates
        cfg = self.config
        nodes = max(cfg.min_nodes, min(cfg.max_nodes, requested_nodes or cfg.default_nodes, max(1, node_count)))
        records = max(cfg.min_records, min(cfg.max_records, requested_records or cfg.default_records))
        explore = min(
            nodes - 1,
            max(0, int(round(nodes * cfg.exploration_fraction * min(1.0, unresolved_rate * 2.0)))),
        )
        if cost_pressure > 0.5 and nodes > cfg.min_nodes:
            nodes = max(cfg.min_nodes, nodes - 1)
            explore = min(explore, nodes - 1)
        token_budget = max(256, int(cfg.default_tokens * (1.0 - 0.35 * min(1.0, cost_pressure))))
        return QueryBudget(nodes, records, token_budget, explore)

    def node_record_cap(self, node_id: str, *, probation: bool = False) -> int:
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("Deluxe node id must be a non-empty string")
        if not isinstance(probation, bool):
            raise ValueError("Deluxe probation flag must be boolean")
        cap = self.config.per_node_record_cap
        return max(1, int(round(cap * self.config.probation_budget_scale))) if probation else cap

    def observe_node_cost(self, node_id: str, cost: float, *, alpha: float = 0.2) -> None:
        self._observe(self.node_cost_ema, node_id, cost, alpha)

    def observe_capability_cost(self, capability_id: str, cost: float, *, alpha: float = 0.2) -> None:
        self._observe(self.capability_cost_ema, capability_id, cost, alpha)

    @staticmethod
    def _observe(target: dict[str, float], key: str, value: float, alpha: float) -> None:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Deluxe cost observation key must be a non-empty string")
        numeric: list[float] = []
        for label, raw in (("value", value), ("alpha", alpha)):
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValueError(f"Deluxe cost observation {label} must be numeric")
            try:
                converted = float(raw)
            except OverflowError as exc:
                raise ValueError(f"Deluxe cost observation {label} must be finite") from exc
            if not math.isfinite(converted):
                raise ValueError(f"Deluxe cost observation {label} must be finite")
            numeric.append(converted)
        value, alpha = numeric
        if value < 0.0 or not 0.0 < alpha <= 1.0:
            raise ValueError("Deluxe cost observation is out of range")
        previous = target.get(key, value)
        if isinstance(previous, bool) or not isinstance(previous, (int, float)):
            raise ValueError("Deluxe prior cost state must be numeric")
        try:
            previous_numeric = float(previous)
        except OverflowError as exc:
            raise ValueError("Deluxe prior cost state must be finite") from exc
        if not math.isfinite(previous_numeric) or previous_numeric < 0.0:
            raise ValueError("Deluxe prior cost state must be finite and non-negative")
        target[key] = (1.0 - alpha) * previous_numeric + alpha * value

    def snapshot(self) -> JsonObject:
        return {
            "node_cost_ema": dict(sorted(self.node_cost_ema.items())),
            "capability_cost_ema": dict(sorted(self.capability_cost_ema.items())),
        }


__all__ = ["FineGrainedBudgetPolicy"]
