from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import re
from typing import Sequence

from ..api import (
    DeluxeMemoryRecord,
    DeluxeServingSource,
    MemoryRuntimeTier,
    QueryBudget,
)
from ...serving import MemoryServingRecord, ServingRuntimeState
from .budget import FineGrainedBudgetPolicy
from .capabilities import CapabilityRegistry
from .capability_security import CapabilityAuthorizer
from .memory_fault import MemoryFaultHandler
from .working_set import ArchitectureOpenWorkingSetPolicy
from .state import capture_deluxe_serving_state, decode_deluxe_serving_state, restore_deluxe_serving_state


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def _tokens(text: str) -> set[str]:
    return {match.group(0).casefold() for match in _TOKEN_RE.finditer(text)}


def _flatten(value: object) -> str:
    if isinstance(value, dict):
        return " ".join(f"{key} {_flatten(item)}" for key, item in sorted(value.items()))
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten(item) for item in value)
    return str(value)


class ResolutionKind(StrEnum):
    BASE = "base"
    FINE = "fine"
    GROUPED = "grouped"
    COMPRESSED = "compressed"


@dataclass(frozen=True, slots=True)
class ResolutionDecision:
    kind: ResolutionKind
    reason: str


class ResolutionRouter:
    """Node-local view selection; views never become architecture sources."""

    def choose(self, *, intent: str, record_count: int, token_budget: int) -> ResolutionDecision:
        if record_count < 0 or token_budget <= 0:
            raise ValueError("Deluxe resolution inputs are invalid")
        words = len(_tokens(intent))
        if record_count <= 4:
            return ResolutionDecision(ResolutionKind.FINE, "small_record_set")
        if token_budget < 900:
            return ResolutionDecision(ResolutionKind.COMPRESSED, "tight_token_budget")
        if words <= 4 and record_count >= 10:
            return ResolutionDecision(ResolutionKind.GROUPED, "broad_short_intent")
        return ResolutionDecision(ResolutionKind.BASE, "default")


@dataclass(frozen=True, slots=True)
class DeluxeQueryDiagnostics:
    tier: MemoryRuntimeTier
    architecture_generation: str
    architecture_digest: str
    capability_ids: tuple[str, ...]
    working_set_nodes: tuple[str, ...]
    resolution_by_node: tuple[tuple[str, str], ...]
    fault_count: int
    token_budget: int
    exploration_slots: int


@dataclass(frozen=True, slots=True)
class DeluxeServingResult:
    generation: str
    context_text: str
    selected_nodes: tuple[str, ...]
    diagnostics: DeluxeQueryDiagnostics
    selected_record_ids: tuple[str, ...] = ()
    selected_source_refs: tuple[str, ...] = ()
    diagnostic_records: tuple[MemoryServingRecord, ...] = ()


@dataclass(frozen=True, slots=True)
class _ProjectedRecord:
    """Ephemeral serving view; it is never written back to method memory."""

    node_id: str
    record_id: str
    sequence: int
    text: str
    payload: dict[str, object]
    source_refs: tuple[str, ...]


def _record_score(intent_tokens: set[str], record: DeluxeMemoryRecord) -> float:
    text = record.text or _flatten(record.payload)
    record_tokens = _tokens(text)
    overlap = len(intent_tokens & record_tokens)
    exact_bonus = 0.25 if any(token in text.casefold() for token in intent_tokens) else 0.0
    return overlap / max(1, len(intent_tokens)) + exact_bonus


def _resolution_view(
    records: Sequence[DeluxeMemoryRecord],
    decision: ResolutionDecision,
    *,
    max_records: int,
) -> tuple[DeluxeMemoryRecord, ...]:
    if max_records <= 0:
        return ()
    if decision.kind in {ResolutionKind.BASE, ResolutionKind.FINE}:
        return tuple(records[:max_records])
    if decision.kind is ResolutionKind.COMPRESSED:
        projected: list[_ProjectedRecord] = []
        for record in records[:max_records]:
            payload = dict(sorted(record.payload.items())[:4])
            text = _flatten(payload) if payload else record.text
            projected.append(
                _ProjectedRecord(
                    record.node_id,
                    record.record_id,
                    record.sequence,
                    text,
                    payload,
                    record.source_refs,
                )
            )
        return tuple(projected)
    groups: dict[str, DeluxeMemoryRecord] = {}
    for record in records:
        key = next(iter(_tokens(record.text or _flatten(record.payload))), record.record_id)
        groups.setdefault(key, record)
    return tuple(groups.values())[:max_records]


@dataclass(slots=True)
class DeluxeMemoryServingService:
    """Explicit Deluxe serving provider over a node-partitioned pinned source."""

    source: DeluxeServingSource
    registry: CapabilityRegistry = field(default_factory=CapabilityRegistry)
    budget_policy: FineGrainedBudgetPolicy = field(default_factory=FineGrainedBudgetPolicy)
    working_set_policy: ArchitectureOpenWorkingSetPolicy | None = None
    fault_handler: MemoryFaultHandler | None = None
    authorizer: CapabilityAuthorizer = field(default_factory=CapabilityAuthorizer)
    unresolved_rate: float = 0.0
    cost_pressure: float = 0.0
    last_diagnostics: DeluxeQueryDiagnostics | None = None

    def __post_init__(self) -> None:
        if self.working_set_policy is None:
            self.working_set_policy = ArchitectureOpenWorkingSetPolicy(self.registry)
        if self.fault_handler is None:
            self.fault_handler = MemoryFaultHandler(self.registry)

    def snapshot_state(self) -> ServingRuntimeState:
        assert self.working_set_policy is not None
        assert self.fault_handler is not None
        return capture_deluxe_serving_state(
            self.registry,
            self.budget_policy,
            self.working_set_policy,
            self.fault_handler,
            unresolved_rate=self.unresolved_rate,
            cost_pressure=self.cost_pressure,
        )

    def validate_state(self, snapshot: ServingRuntimeState) -> None:
        decode_deluxe_serving_state(snapshot)

    def restore_state(self, snapshot: ServingRuntimeState) -> None:
        assert self.working_set_policy is not None
        assert self.fault_handler is not None
        state = restore_deluxe_serving_state(
            snapshot,
            self.registry,
            self.budget_policy,
            self.working_set_policy,
            self.fault_handler,
        )
        self.unresolved_rate = state.unresolved_rate
        self.cost_pressure = state.cost_pressure
        self.last_diagnostics = None

    def recall(self, intent: str, *, limit: int) -> DeluxeServingResult:
        if not intent.strip() or limit <= 0:
            raise ValueError("Deluxe recall intent and limit must be positive")
        snapshot = self.source.open_deluxe_snapshot()
        architecture = snapshot.architecture
        if snapshot.generation != architecture.generation:
            raise ValueError("Deluxe read snapshot generation does not match architecture generation")
        available_nodes = set(snapshot.node_ids())
        architecture_nodes = {node.node_id for node in architecture.nodes}
        if available_nodes - architecture_nodes:
            raise ValueError("Deluxe read snapshot contains records outside pinned architecture")

        self.registry.tick_query()
        self.registry.sync_architecture(architecture)
        budget = self.budget_policy.allocate(
            requested_nodes=limit,
            requested_records=limit,
            node_count=len(architecture.nodes),
            unresolved_rate=self.unresolved_rate,
            cost_pressure=self.cost_pressure,
        )
        ranked_all = self.registry.discover(intent, include_dormant=True)
        disclosed_limit = max(1, min(len(ranked_all), budget.node_limit * 3))
        disclosed_cards = tuple(card for _, card in ranked_all[:disclosed_limit])
        token = self.authorizer.issue(role="executor", cards=disclosed_cards)
        ranked = tuple(
            (score, card)
            for score, card in ranked_all[:disclosed_limit]
            if self.authorizer.authorize(token, card.capability_id)
        )
        assert self.working_set_policy is not None
        assert self.fault_handler is not None
        working_set = self.working_set_policy.select(
            ranked,
            budget_nodes=budget.node_limit,
            exploration_slots=budget.exploration_slots,
        )
        retrieved, resolution_by_node, useful_nodes = self._retrieve(
            intent=intent,
            snapshot=snapshot,
            working_set=working_set,
            budget=budget,
        )
        faults_before = len(self.fault_handler.faults)
        if not retrieved or max((row[2] for row in retrieved), default=0.0) <= 0.05:
            recovered = self.fault_handler.recover_if_needed(
                intent=intent,
                working_set=working_set,
                ranked_capabilities=ranked,
                hard_limit=budget.node_limit,
            )
            if recovered.node_ids != working_set.node_ids:
                working_set = recovered
                retrieved, resolution_by_node, useful_nodes = self._retrieve(
                    intent=intent,
                    snapshot=snapshot,
                    working_set=working_set,
                    budget=budget,
                )
        self.registry.observe_selection(
            working_set.capability_ids,
            useful_provider_ids=useful_nodes,
            utility=max((row[2] for row in retrieved), default=0.0),
        )
        diagnostics = DeluxeQueryDiagnostics(
            tier=MemoryRuntimeTier.DELUXE,
            architecture_generation=architecture.generation,
            architecture_digest=architecture.digest,
            capability_ids=working_set.capability_ids,
            working_set_nodes=working_set.node_ids,
            resolution_by_node=tuple(sorted(resolution_by_node.items())),
            fault_count=len(self.fault_handler.faults) - faults_before,
            token_budget=budget.token_budget,
            exploration_slots=budget.exploration_slots,
        )
        self.last_diagnostics = diagnostics
        selected_nodes = tuple(dict.fromkeys(row[0] for row in retrieved))
        selected_record_ids = tuple(dict.fromkeys(row[3] for row in retrieved))
        selected_source_refs = tuple(sorted({ref for row in retrieved for ref in row[4]}))
        return DeluxeServingResult(
            generation=snapshot.generation,
            context_text="\n".join(row[1] for row in retrieved),
            selected_nodes=selected_nodes,
            diagnostics=diagnostics,
            selected_record_ids=selected_record_ids,
            selected_source_refs=selected_source_refs,
            diagnostic_records=tuple(
                MemoryServingRecord(
                    node_id=row[0],
                    record_id=row[3],
                    score=row[2],
                    payload={"text": row[1]},
                    source_refs=row[4],
                )
                for row in retrieved
            ),
        )

    def runtime_report(self) -> dict[str, object]:
        """Return the complete read-side Deluxe runtime state for observability.

        This is a derived report.  It does not expose a writer, change a
        budget, or grant any capability to the caller.
        """

        snapshot = self.source.open_deluxe_snapshot()
        record_counts = {
            node_id: sum(1 for _ in snapshot.iter_records(node_id))
            for node_id in snapshot.node_ids()
        }
        faults = tuple(self.fault_handler.faults) if self.fault_handler is not None else ()
        diagnostics = self.last_diagnostics
        return {
            "tier": MemoryRuntimeTier.DELUXE.value,
            "generation": snapshot.generation,
            "architecture_generation": snapshot.architecture.generation,
            "architecture_digest": snapshot.architecture.digest,
            "record_counts": record_counts,
            "capability_registry": dict(self.registry.snapshot()),
            "budget_policy": dict(self.budget_policy.snapshot()),
            "memory_faults": [
                {
                    "fault_id": fault.fault_id,
                    "intent": fault.intent,
                    "missing_capability_id": fault.missing_capability_id,
                    "missing_node_id": fault.missing_node_id,
                    "reason": fault.reason,
                    "recovered": fault.recovered,
                }
                for fault in faults
            ],
            "last_query": None
            if diagnostics is None
            else {
                "capability_ids": diagnostics.capability_ids,
                "working_set_nodes": diagnostics.working_set_nodes,
                "resolution_by_node": diagnostics.resolution_by_node,
                "fault_count": diagnostics.fault_count,
                "token_budget": diagnostics.token_budget,
                "exploration_slots": diagnostics.exploration_slots,
            },
        }

    @staticmethod
    def _retrieve(*, intent: str, snapshot, working_set, budget: QueryBudget):
        intent_tokens = _tokens(intent)
        retrieved: list[tuple[str, str, float, str, tuple[str, ...]]] = []
        resolution_by_node: dict[str, str] = {}
        useful_nodes: set[str] = set()
        router = ResolutionRouter()
        for entry in working_set.entries:
            records = tuple(snapshot.iter_records(entry.node_id))
            cap = min(budget.record_limit, 8)
            decision = router.choose(
                intent=intent,
                record_count=len(records),
                token_budget=budget.token_budget,
            )
            resolution_by_node[entry.node_id] = decision.kind.value
            for record in _resolution_view(records, decision, max_records=cap):
                score = entry.score + _record_score(intent_tokens, record)
                if score > 0.05:
                    useful_nodes.add(entry.node_id)
                retrieved.append(
                    (
                        entry.node_id,
                        record.text or _flatten(record.payload),
                        score,
                        record.record_id,
                        tuple(record.source_refs),
                    )
                )
        retrieved.sort(key=lambda row: (-row[2], row[0], row[1]))
        return retrieved[: budget.record_limit], resolution_by_node, useful_nodes


__all__ = [
    "DeluxeMemoryServingService",
    "DeluxeQueryDiagnostics",
    "DeluxeServingResult",
    "ResolutionDecision",
    "ResolutionKind",
    "ResolutionRouter",
]
