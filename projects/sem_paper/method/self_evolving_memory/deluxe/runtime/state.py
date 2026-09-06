from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math

from ..api import CapabilityCard, CapabilityLifecycle, CapabilityState, MemoryFault
from ...serving import ServingRuntimeState
from .budget import FineGrainedBudgetPolicy
from .capabilities import CapabilityRegistry
from .memory_fault import MemoryFaultHandler
from .working_set import ArchitectureOpenWorkingSetPolicy


STATE_KIND = "sem.deluxe.adaptive_serving"
STATE_SCHEMA_VERSION = "1"


@dataclass(frozen=True, slots=True)
class CapabilityRuntimeState:
    card: CapabilityCard
    state: CapabilityState
    age_queries: int
    selected_queries: int
    useful_queries: int
    last_selected_query: int
    probation_queries_remaining: int
    lease_queries_remaining: int
    utility_ema: float

    def __post_init__(self) -> None:
        if not isinstance(self.card, CapabilityCard):
            raise ValueError("Deluxe capability runtime card must be typed")
        if not isinstance(self.state, CapabilityState):
            raise ValueError("Deluxe capability runtime state must be typed")
        for label, values in (("access", self.card.access), ("output types", self.card.output_types)):
            if (
                not isinstance(values, tuple)
                or any(not isinstance(value, str) or not value.strip() for value in values)
                or len(values) != len(set(values))
            ):
                raise ValueError(f"Deluxe capability {label} must be unique non-empty strings")
        counts = (
            self.age_queries,
            self.selected_queries,
            self.useful_queries,
            self.probation_queries_remaining,
            self.lease_queries_remaining,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts):
            raise ValueError("Deluxe capability runtime counts must be non-negative integers")
        if isinstance(self.last_selected_query, bool) or not isinstance(self.last_selected_query, int) or self.last_selected_query < -1:
            raise ValueError("Deluxe capability last-selected query is invalid")
        if self.useful_queries > self.selected_queries:
            raise ValueError("Deluxe useful query count cannot exceed selected query count")
        if isinstance(self.utility_ema, bool) or not isinstance(self.utility_ema, (int, float)):
            raise ValueError("Deluxe capability utility EMA must be numeric")
        try:
            utility_ema = float(self.utility_ema)
        except OverflowError as exc:
            raise ValueError("Deluxe capability utility EMA must be finite") from exc
        if not math.isfinite(utility_ema):
            raise ValueError("Deluxe capability utility EMA must be finite")
        object.__setattr__(self, "utility_ema", utility_ema)

    @classmethod
    def capture(cls, card: CapabilityCard, lifecycle: CapabilityLifecycle) -> "CapabilityRuntimeState":
        return cls(
            card,
            lifecycle.state,
            lifecycle.age_queries,
            lifecycle.selected_queries,
            lifecycle.useful_queries,
            lifecycle.last_selected_query,
            lifecycle.probation_queries_remaining,
            lifecycle.lease_queries_remaining,
            lifecycle.utility_ema,
        )

    def materialize_lifecycle(self) -> CapabilityLifecycle:
        return CapabilityLifecycle(
            state=self.state,
            age_queries=self.age_queries,
            selected_queries=self.selected_queries,
            useful_queries=self.useful_queries,
            last_selected_query=self.last_selected_query,
            probation_queries_remaining=self.probation_queries_remaining,
            lease_queries_remaining=self.lease_queries_remaining,
            utility_ema=self.utility_ema,
        )


@dataclass(frozen=True, slots=True)
class DeluxeServingRuntimeState:
    query_clock: int
    architecture_generation: str | None
    architecture_digest: str | None
    capabilities: tuple[CapabilityRuntimeState, ...]
    budget_node_costs: tuple[tuple[str, float], ...]
    budget_capability_costs: tuple[tuple[str, float], ...]
    working_set_utility: tuple[tuple[str, float], ...]
    working_set_reliability: tuple[tuple[str, float], ...]
    working_set_cost: tuple[tuple[str, float], ...]
    faults: tuple[MemoryFault, ...]
    unresolved_rate: float
    cost_pressure: float

    def __post_init__(self) -> None:
        if isinstance(self.query_clock, bool) or not isinstance(self.query_clock, int) or self.query_clock < 0:
            raise ValueError("Deluxe serving query clock must be a non-negative integer")
        if (self.architecture_generation is None) != (self.architecture_digest is None):
            raise ValueError("Deluxe architecture generation/digest must be present together")
        if self.architecture_generation is not None and (
            not isinstance(self.architecture_generation, str)
            or not self.architecture_generation.strip()
            or not isinstance(self.architecture_digest, str)
            or not self.architecture_digest.strip()
        ):
            raise ValueError("Deluxe architecture state identity must be non-empty strings")
        if not isinstance(self.capabilities, tuple) or any(
            not isinstance(row, CapabilityRuntimeState) for row in self.capabilities
        ):
            raise ValueError("Deluxe serving capabilities must be typed")
        ids = tuple(row.card.capability_id for row in self.capabilities)
        if len(ids) != len(set(ids)):
            raise ValueError("Deluxe serving state contains duplicate capabilities")
        for name, pairs in (
            ("budget node costs", self.budget_node_costs),
            ("budget capability costs", self.budget_capability_costs),
            ("working-set utility", self.working_set_utility),
            ("working-set reliability", self.working_set_reliability),
            ("working-set cost", self.working_set_cost),
        ):
            if not isinstance(pairs, tuple):
                raise ValueError(f"Deluxe {name} must be a tuple")
            keys: list[str] = []
            for pair in pairs:
                if not isinstance(pair, tuple) or len(pair) != 2:
                    raise ValueError(f"Deluxe {name} entries must be pairs")
                key, value = pair
                if not isinstance(key, str) or not key.strip():
                    raise ValueError(f"Deluxe {name} contains invalid keys")
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"Deluxe {name} must contain numeric values")
                try:
                    numeric = float(value)
                except OverflowError as exc:
                    raise ValueError(f"Deluxe {name} must contain finite values") from exc
                if not math.isfinite(numeric):
                    raise ValueError(f"Deluxe {name} must contain finite values")
                keys.append(key)
            if len(keys) != len(set(keys)):
                raise ValueError(f"Deluxe {name} contains duplicate keys")
        if any(value < 0.0 for _, value in (*self.budget_node_costs, *self.budget_capability_costs, *self.working_set_cost)):
            raise ValueError("Deluxe cost state cannot be negative")
        if any(not 0.0 <= value <= 1.0 for _, value in self.working_set_reliability):
            raise ValueError("Deluxe working-set reliability must be in [0,1]")
        normalized_rates: list[float] = []
        for label, value in (("unresolved rate", self.unresolved_rate), ("cost pressure", self.cost_pressure)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"Deluxe {label} must be numeric")
            try:
                numeric = float(value)
            except OverflowError as exc:
                raise ValueError(f"Deluxe {label} must be finite and non-negative") from exc
            if not math.isfinite(numeric) or numeric < 0.0:
                raise ValueError(f"Deluxe {label} must be finite and non-negative")
            normalized_rates.append(numeric)
        object.__setattr__(self, "unresolved_rate", normalized_rates[0])
        object.__setattr__(self, "cost_pressure", normalized_rates[1])
        if not isinstance(self.faults, tuple) or any(not isinstance(fault, MemoryFault) for fault in self.faults):
            raise ValueError("Deluxe serving faults must be typed")
        for fault in self.faults:
            identities = (fault.fault_id, fault.intent, fault.missing_capability_id, fault.missing_node_id, fault.reason)
            if any(not isinstance(value, str) or not value.strip() for value in identities):
                raise ValueError("Deluxe serving fault identity fields must be non-empty strings")
            if not isinstance(fault.recovered, bool):
                raise ValueError("Deluxe serving fault recovered must be boolean")
        fault_ids = tuple(fault.fault_id for fault in self.faults)
        if len(fault_ids) != len(set(fault_ids)):
            raise ValueError("Deluxe serving state contains duplicate fault ids")


def _pairs(mapping: Mapping[str, float]) -> tuple[tuple[str, float], ...]:
    result: list[tuple[str, float]] = []
    for key, value in mapping.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Deluxe serving state map keys must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Deluxe serving state map values must be numeric")
        try:
            numeric = float(value)
        except OverflowError as exc:
            raise ValueError("Deluxe serving state map values must be finite") from exc
        if not math.isfinite(numeric):
            raise ValueError("Deluxe serving state map values must be finite")
        result.append((key, numeric))
    return tuple(sorted(result))


def capture_deluxe_serving_state(
    registry: CapabilityRegistry,
    budget: FineGrainedBudgetPolicy,
    working_set: ArchitectureOpenWorkingSetPolicy,
    faults: MemoryFaultHandler,
    *,
    unresolved_rate: float,
    cost_pressure: float,
) -> ServingRuntimeState:
    state = DeluxeServingRuntimeState(
        query_clock=registry.query_clock,
        architecture_generation=registry.architecture_generation,
        architecture_digest=registry.architecture_digest,
        capabilities=tuple(
            CapabilityRuntimeState.capture(registry.cards[capability_id], registry.lifecycle[capability_id])
            for capability_id in sorted(registry.cards)
        ),
        budget_node_costs=_pairs(budget.node_cost_ema),
        budget_capability_costs=_pairs(budget.capability_cost_ema),
        working_set_utility=_pairs(working_set.provider_utility),
        working_set_reliability=_pairs(working_set.provider_reliability),
        working_set_cost=_pairs(working_set.provider_cost),
        faults=tuple(faults.faults),
        unresolved_rate=unresolved_rate,
        cost_pressure=cost_pressure,
    )
    payload = {
        "query_clock": state.query_clock,
        "architecture_generation": state.architecture_generation,
        "architecture_digest": state.architecture_digest,
        "capabilities": [
            {
                "card": {
                    "capability_id": row.card.capability_id,
                    "provider_node_id": row.card.provider_node_id,
                    "purpose": row.card.purpose,
                    "access": list(row.card.access),
                    "output_types": list(row.card.output_types),
                    "scope": row.card.scope,
                    "generation_created": row.card.generation_created,
                },
                "lifecycle": {
                    "state": row.state.value,
                    "age_queries": row.age_queries,
                    "selected_queries": row.selected_queries,
                    "useful_queries": row.useful_queries,
                    "last_selected_query": row.last_selected_query,
                    "probation_queries_remaining": row.probation_queries_remaining,
                    "lease_queries_remaining": row.lease_queries_remaining,
                    "utility_ema": row.utility_ema,
                },
            }
            for row in state.capabilities
        ],
        "budget_node_costs": dict(state.budget_node_costs),
        "budget_capability_costs": dict(state.budget_capability_costs),
        "working_set_utility": dict(state.working_set_utility),
        "working_set_reliability": dict(state.working_set_reliability),
        "working_set_cost": dict(state.working_set_cost),
        "faults": [
            {
                "fault_id": fault.fault_id,
                "intent": fault.intent,
                "missing_capability_id": fault.missing_capability_id,
                "missing_node_id": fault.missing_node_id,
                "reason": fault.reason,
                "recovered": fault.recovered,
            }
            for fault in state.faults
        ],
        "unresolved_rate": state.unresolved_rate,
        "cost_pressure": state.cost_pressure,
    }
    return ServingRuntimeState(STATE_KIND, STATE_SCHEMA_VERSION, payload)


def _require_object(value: object, label: str, *, fields: set[str] | None = None) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Deluxe serving state {label} must be an object")
    if fields is not None and set(value) != fields:
        raise ValueError(f"Deluxe serving state {label} fields are not exact")
    return value


def _require_array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"Deluxe serving state {label} must be an array")
    return value


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Deluxe serving state {label} must be a non-empty string")
    return value


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, label)


def _require_int(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"Deluxe serving state {label} must be an integer >= {minimum}")
    return value


def _require_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Deluxe serving state {label} must be numeric")
    try:
        numeric = float(value)
    except OverflowError as exc:
        raise ValueError(f"Deluxe serving state {label} must be finite") from exc
    if not math.isfinite(numeric):
        raise ValueError(f"Deluxe serving state {label} must be finite")
    return numeric


def _require_string_array(value: object, label: str) -> tuple[str, ...]:
    rows = _require_array(value, label)
    result = tuple(_require_text(item, f"{label} entry") for item in rows)
    if len(result) != len(set(result)):
        raise ValueError(f"Deluxe serving state {label} entries must be unique")
    return result


def _decode_float_map(value: object, label: str) -> tuple[tuple[str, float], ...]:
    mapping = _require_object(value, label)
    result = tuple(sorted(
        (_require_text(key, f"{label} key"), _require_number(raw, f"{label}[{key!r}]"))
        for key, raw in mapping.items()
    ))
    return result


def decode_deluxe_serving_state(snapshot: ServingRuntimeState) -> DeluxeServingRuntimeState:
    if not isinstance(snapshot, ServingRuntimeState):
        raise ValueError("Deluxe serving checkpoint must be a ServingRuntimeState")
    if snapshot.state_kind != STATE_KIND or snapshot.schema_version != STATE_SCHEMA_VERSION:
        raise ValueError("Deluxe serving checkpoint identity mismatch")
    expected = {
        "query_clock", "architecture_generation", "architecture_digest", "capabilities",
        "budget_node_costs", "budget_capability_costs", "working_set_utility",
        "working_set_reliability", "working_set_cost", "faults", "unresolved_rate", "cost_pressure",
    }
    payload = _require_object(snapshot.payload, "payload", fields=expected)
    query_clock = _require_int(payload["query_clock"], "query_clock")
    generation = _optional_text(payload["architecture_generation"], "architecture_generation")
    digest = _optional_text(payload["architecture_digest"], "architecture_digest")
    if (generation is None) != (digest is None):
        raise ValueError("Deluxe serving checkpoint architecture identity must be present together")

    raw_capabilities = _require_array(payload["capabilities"], "capabilities")
    capabilities: list[CapabilityRuntimeState] = []
    card_fields = {"capability_id", "provider_node_id", "purpose", "access", "output_types", "scope", "generation_created"}
    lifecycle_fields = {
        "state", "age_queries", "selected_queries", "useful_queries", "last_selected_query",
        "probation_queries_remaining", "lease_queries_remaining", "utility_ema",
    }
    for item in raw_capabilities:
        row = _require_object(item, "capability", fields={"card", "lifecycle"})
        card_row = _require_object(row["card"], "capability card", fields=card_fields)
        life_row = _require_object(row["lifecycle"], "capability lifecycle", fields=lifecycle_fields)
        card = CapabilityCard(
            capability_id=_require_text(card_row["capability_id"], "capability_id"),
            provider_node_id=_require_text(card_row["provider_node_id"], "provider_node_id"),
            purpose=_require_text(card_row["purpose"], "purpose"),
            access=_require_string_array(card_row["access"], "access"),
            output_types=_require_string_array(card_row["output_types"], "output_types"),
            scope=_require_text(card_row["scope"], "scope"),
            generation_created=_require_text(card_row["generation_created"], "generation_created"),
        )
        state_raw = _require_text(life_row["state"], "capability lifecycle state")
        try:
            lifecycle_state = CapabilityState(state_raw)
        except ValueError as exc:
            raise ValueError("Deluxe capability lifecycle state is invalid") from exc
        capabilities.append(CapabilityRuntimeState(
            card=card,
            state=lifecycle_state,
            age_queries=_require_int(life_row["age_queries"], "age_queries"),
            selected_queries=_require_int(life_row["selected_queries"], "selected_queries"),
            useful_queries=_require_int(life_row["useful_queries"], "useful_queries"),
            last_selected_query=_require_int(life_row["last_selected_query"], "last_selected_query", minimum=-1),
            probation_queries_remaining=_require_int(life_row["probation_queries_remaining"], "probation_queries_remaining"),
            lease_queries_remaining=_require_int(life_row["lease_queries_remaining"], "lease_queries_remaining"),
            utility_ema=_require_number(life_row["utility_ema"], "utility_ema"),
        ))

    raw_faults = _require_array(payload["faults"], "faults")
    fault_fields = {"fault_id", "intent", "missing_capability_id", "missing_node_id", "reason", "recovered"}
    faults: list[MemoryFault] = []
    for item in raw_faults:
        row = _require_object(item, "fault", fields=fault_fields)
        recovered = row["recovered"]
        if not isinstance(recovered, bool):
            raise ValueError("Deluxe serving state fault recovered must be boolean")
        faults.append(MemoryFault(
            _require_text(row["fault_id"], "fault_id"),
            _require_text(row["intent"], "fault intent"),
            _require_text(row["missing_capability_id"], "missing_capability_id"),
            _require_text(row["missing_node_id"], "missing_node_id"),
            _require_text(row["reason"], "fault reason"),
            recovered,
        ))

    return DeluxeServingRuntimeState(
        query_clock=query_clock,
        architecture_generation=generation,
        architecture_digest=digest,
        capabilities=tuple(capabilities),
        budget_node_costs=_decode_float_map(payload["budget_node_costs"], "budget_node_costs"),
        budget_capability_costs=_decode_float_map(payload["budget_capability_costs"], "budget_capability_costs"),
        working_set_utility=_decode_float_map(payload["working_set_utility"], "working_set_utility"),
        working_set_reliability=_decode_float_map(payload["working_set_reliability"], "working_set_reliability"),
        working_set_cost=_decode_float_map(payload["working_set_cost"], "working_set_cost"),
        faults=tuple(faults),
        unresolved_rate=_require_number(payload["unresolved_rate"], "unresolved_rate"),
        cost_pressure=_require_number(payload["cost_pressure"], "cost_pressure"),
    )

def restore_deluxe_serving_state(
    snapshot: ServingRuntimeState,
    registry: CapabilityRegistry,
    budget: FineGrainedBudgetPolicy,
    working_set: ArchitectureOpenWorkingSetPolicy,
    faults: MemoryFaultHandler,
) -> DeluxeServingRuntimeState:
    state = decode_deluxe_serving_state(snapshot)
    registry.query_clock = state.query_clock
    registry.architecture_generation = state.architecture_generation
    registry.architecture_digest = state.architecture_digest
    registry.cards = {row.card.capability_id: row.card for row in state.capabilities}
    registry.lifecycle = {row.card.capability_id: row.materialize_lifecycle() for row in state.capabilities}
    budget.node_cost_ema = dict(state.budget_node_costs)
    budget.capability_cost_ema = dict(state.budget_capability_costs)
    working_set.provider_utility = dict(state.working_set_utility)
    working_set.provider_reliability = dict(state.working_set_reliability)
    working_set.provider_cost = dict(state.working_set_cost)
    faults.faults = list(state.faults)
    return state


__all__ = [
    "CapabilityRuntimeState",
    "DeluxeServingRuntimeState",
    "STATE_KIND",
    "STATE_SCHEMA_VERSION",
    "capture_deluxe_serving_state",
    "decode_deluxe_serving_state",
    "restore_deluxe_serving_state",
]
