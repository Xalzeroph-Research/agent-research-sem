from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from noetrium.contracts import (
    MethodIdentity,
    MethodProgramIdentity,
    MethodSnapshot,
    MethodTaskCompletionReceipt,
    MethodTaskOutcome,
    RecallRequest,
    RecallResult,
    canonical_bytes,
    canonical_digest,
)
from noetrium_platform.capabilities.participant.agent.api.memory_graph import (
    MemoryEdgeRecord,
    MemoryGraphLedgerEntry,
    MemoryGraphOperation,
    MemoryGraphSnapshot,
    MemoryNodeRecord,
)
from noetrium_platform.capabilities.participant.agent.runtime.memory_graph import (
    MemoryGraphConflict,
    VersionedMemoryGraph,
)


SEM_TREATMENTS = frozenset({"no_memory", "flat_episodic", "fixed_typed", "sem"})
SEM_METHOD_ID = "self_evolving_memory"


def _tokens(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9_\-:]+", value.lower())
        if len(token) > 1
    }


@dataclass(frozen=True, slots=True)
class MemoryEntry:
    entry_id: str
    text: str
    source: str
    generation: str
    digest: str


@dataclass(frozen=True, slots=True)
class EvidenceEvent:
    evidence_id: str
    task_id: str
    family: str
    payload: Mapping[str, Any]
    source: str
    generation: str
    digest: str

    @classmethod
    def build(
        cls,
        *,
        task_id: str,
        family: str,
        payload: Mapping[str, Any],
        source: str,
        generation: str,
    ) -> "EvidenceEvent":
        frozen_payload = json.loads(
            json.dumps(dict(payload), sort_keys=True, ensure_ascii=False, default=str)
        )
        digest = canonical_digest({
            "task_id": task_id,
            "family": family,
            "payload": frozen_payload,
            "source": source,
            "generation": generation,
        })
        return cls(
            f"evidence:{digest[:24]}",
            task_id,
            family,
            frozen_payload,
            source,
            generation,
            digest,
        )


@dataclass(frozen=True, slots=True)
class StructuralDemand:
    demand_id: str
    task_id: str
    family: str
    signal: str
    operation: str
    evidence_ids: tuple[str, ...]
    target_ids: tuple[str, ...]
    digest: str


@dataclass(frozen=True, slots=True)
class SemanticEdit:
    edit_id: str
    operation: str
    target_id: str
    payload: Mapping[str, Any]
    rationale: str
    digest: str


@dataclass(frozen=True, slots=True)
class EvolutionEdit:
    """Compatibility view for callers that only need an edit receipt."""

    edit_id: str
    rationale: str
    replacement: str
    digest: str


@dataclass(frozen=True, slots=True)
class EvolutionCandidate:
    candidate_id: str
    demand: StructuralDemand
    edits: tuple[SemanticEdit, ...]
    status: str
    reason: str
    base_graph_digest: str
    backfill_ids: tuple[str, ...]
    digest: str


class SEMMethodSession:
    """SEM's method-owned semantic memory lifecycle.

    The platform owns generic graph storage, snapshot identity, ordering,
    acyclicity, and atomic activation. SEM owns evidence interpretation,
    structural-demand detection, semantic edit planning, and historical
    backfill. Minecraft task logic is intentionally outside this class.
    """

    task_completion_idempotency = "sem.method-task-completion.v3"

    def __init__(
        self,
        *,
        session_id: str,
        treatment_id: str,
        seed: str,
        adaptive: bool | None = None,
        initial_memory: tuple[str, ...] = (),
    ) -> None:
        if not session_id.strip() or not seed.strip():
            raise ValueError("SEM session identity is required")
        if treatment_id not in SEM_TREATMENTS:
            raise ValueError(f"unknown SEM treatment: {treatment_id}")
        if adaptive is not None and adaptive != (treatment_id == "sem"):
            raise ValueError("adaptive flag must agree with the SEM treatment")
        self.session_id = session_id
        self.treatment_id = treatment_id
        self.seed = seed
        self.adaptive = treatment_id == "sem"
        self._closed = False
        self._queries = 0
        self._completed: set[str] = set()
        self._entries: list[MemoryEntry] = []
        self._evidence: list[EvidenceEvent] = []
        self._demands: list[StructuralDemand] = []
        self._candidates: list[EvolutionCandidate] = []
        self._evolution_events: list[dict[str, Any]] = []
        self._candidate_count = 0
        self._adopted_count = 0
        self._rejected_count = 0
        self._backfilled_count = 0
        self._mismatch_count = 0
        self._graph = VersionedMemoryGraph(self._initial_snapshot(treatment_id))
        for text in initial_memory:
            self.ingest({"text": text, "source": "initial"}, None)

    @staticmethod
    def _initial_snapshot(treatment_id: str) -> MemoryGraphSnapshot:
        if treatment_id == "no_memory":
            return MemoryGraphSnapshot("g0", (), ())
        if treatment_id == "flat_episodic":
            nodes = (
                MemoryNodeRecord(
                    "memory:episodic", "episodic", "episodic",
                    "Chronological episodic evidence.", "g0",
                ),
            )
            return MemoryGraphSnapshot("g0", nodes, ())
        nodes = (
            MemoryNodeRecord(
                "memory:context", "state", "context",
                "Grounded world state and task context.", "g0",
            ),
            MemoryNodeRecord(
                "memory:episode", "episode", "episode",
                "Action and interaction episodes.", "g0",
                parent_ids=("memory:context",),
            ),
            MemoryNodeRecord(
                "memory:outcome", "outcome", "outcome",
                "Task outcomes and verified effects.", "g0",
                parent_ids=("memory:episode",),
            ),
        )
        edges = (
            MemoryEdgeRecord("memory:context", "memory:episode", "contains"),
            MemoryEdgeRecord("memory:episode", "memory:outcome", "produces"),
        )
        return MemoryGraphSnapshot("g0", nodes, edges)

    @property
    def generation(self) -> str:
        return self._graph.snapshot().generation

    @property
    def program_identity(self) -> MethodProgramIdentity:
        return MethodProgramIdentity(
            MethodIdentity(SEM_METHOD_ID, "3.0.0", "1", "1"),
            canonical_digest({
                "treatment": self.treatment_id,
                "initial_architecture": self._initial_snapshot(self.treatment_id).digest(),
            }),
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("SEM session is closed")

    @staticmethod
    def _payload_text(payload: Mapping[str, Any]) -> str:
        return json.dumps(dict(payload), sort_keys=True, ensure_ascii=False, default=str)

    def _append_entry(self, payload: Mapping[str, Any], source: str) -> MemoryEntry:
        text = self._payload_text(payload)
        entry_id = f"entry:{len(self._entries):08d}"
        entry = MemoryEntry(
            entry_id, text, source, self.generation,
            canonical_digest({"entry_id": entry_id, "text": text, "source": source}),
        )
        self._entries.append(entry)
        return entry

    def _record_evidence(
        self,
        payload: Mapping[str, Any],
        *,
        source: str,
        task_id: str = "",
        family: str = "",
    ) -> EvidenceEvent:
        task_id = task_id or str(payload.get("task_id", "session"))
        family = family or str(payload.get("family", "session"))
        event = EvidenceEvent.build(
            task_id=task_id,
            family=family,
            payload=payload,
            source=source,
            generation=self.generation,
        )
        if event.evidence_id not in {item.evidence_id for item in self._evidence}:
            self._evidence.append(event)
            self._append_entry(payload, source)
        return event

    def _update_node_evidence(self, node_id: str, evidence_id: str) -> None:
        snapshot = self._graph.snapshot()
        node = snapshot.node(node_id)
        if node is None or evidence_id in node.evidence_ids:
            return
        operation = MemoryGraphOperation(
            "update_node",
            node_id,
            {
                "evidence_ids": tuple((*node.evidence_ids, evidence_id)),
                "content": node.content,
                "kind": node.kind,
                "label": node.label,
                "parent_ids": node.parent_ids,
                "active": node.active,
            },
        )
        try:
            transaction = self._graph.stage(
                (operation,),
                evidence_ids=(evidence_id,),
                rationale_digest=canonical_digest({"reason": "evidence_ingest"}),
            )
            self._graph.activate(transaction)
        except MemoryGraphConflict:
            self._evolution_events.append({
                "event": "evidence_update_conflict",
                "evidence_id": evidence_id,
                "node_id": node_id,
            })

    def _route_evidence(self, event: EvidenceEvent) -> None:
        if self.treatment_id == "no_memory":
            return
        if self.treatment_id == "flat_episodic":
            self._update_node_evidence("memory:episodic", event.evidence_id)
            return
        payload = event.payload
        targets: list[str] = []
        if any(key in payload for key in ("state", "observation", "position", "inventory")):
            targets.append("memory:context")
        if any(key in payload for key in ("action", "actions", "receipt")):
            targets.append("memory:episode")
        if any(key in payload for key in ("success", "failure_reason", "utility")):
            targets.append("memory:outcome")
        if not targets:
            targets.append("memory:episode")
        for node_id in targets:
            self._update_node_evidence(node_id, event.evidence_id)

    def ingest(self, evidence: Any, context: object) -> None:
        self._ensure_open()
        if isinstance(evidence, Mapping):
            payload = dict(evidence)
        else:
            payload = {"text": str(evidence)}
        event = self._record_evidence(payload, source="environment")
        self._route_evidence(event)

    def recall(self, request: RecallRequest) -> RecallResult:
        self._ensure_open()
        self._queries += 1
        if self.treatment_id == "no_memory":
            return RecallResult("", self.generation, ())
        query = _tokens(str(request.intent))
        selected: list[tuple[int, int, EvidenceEvent]] = []
        for index, event in enumerate(self._evidence):
            text = self._payload_text(event.payload)
            overlap = len(query & _tokens(text + " " + event.family))
            recency = min(index, 20)
            selected.append((overlap * 10 + recency, index, event))
        selected.sort(key=lambda item: (-item[0], -item[1]))
        limit = max(1, int(request.limit))
        chosen = [item[2] for item in selected[:limit]]
        return RecallResult(
            "\n".join(self._payload_text(item.payload) for item in chosen),
            self.generation,
            tuple(item.evidence_id for item in chosen),
        )

    def plan_actions(self, task: Mapping[str, Any]) -> tuple[tuple[str, Mapping[str, Any], float], ...]:
        """Return only an externally supplied plan; SEM does not own Minecraft policy."""
        rows = task.get("action_plan", ())
        if not isinstance(rows, (tuple, list)):
            return ()
        plan: list[tuple[str, Mapping[str, Any], float]] = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            action_type = str(row.get("action_type", "")).strip()
            if not action_type:
                continue
            plan.append((action_type, dict(row.get("arguments", {})), float(row.get("timeout_s", 90.0))))
        return tuple(plan)

    def task_completion_key(self, context: object) -> str:
        if isinstance(context, Mapping) and context.get("task_id"):
            return canonical_digest({"session": self.session_id, "task_id": str(context["task_id"])})
        return canonical_digest({"session": self.session_id, "context": str(context)})

    def _coerce_outcome(self, result: object) -> MethodTaskOutcome:
        if isinstance(result, MethodTaskOutcome):
            return result
        if isinstance(result, Mapping):
            return MethodTaskOutcome(
                task_id=str(result["task_id"]),
                family=str(result.get("family", "unknown")),
                lineage_id=str(result.get("lineage_id", result["task_id"])),
                success=bool(result["success"]),
                utility=float(result.get("utility", 0.0)),
                steps=int(result.get("steps", 0)),
                failure_reason=str(result.get("failure_reason", "")),
                memory_queries=int(result.get("memory_queries", self._queries)),
            )
        raise TypeError("SEM task completion requires MethodTaskOutcome or mapping")

    def _detect_demand(self, outcome: MethodTaskOutcome) -> StructuralDemand:
        failure = outcome.failure_reason.strip().lower() or "unresolved_outcome"
        matching = [
            event for event in self._evidence
            if event.family == outcome.family
            and (
                event.payload.get("failure_reason", "").strip().lower() == failure
                or not event.payload.get("success", True)
            )
        ]
        operation = "create"
        target_ids: tuple[str, ...] = ()
        explicit = next(
            (
                event.payload.get("semantic_demand")
                for event in reversed(self._evidence)
                if isinstance(event.payload.get("semantic_demand"), Mapping)
            ),
            None,
        )
        if isinstance(explicit, Mapping):
            operation = str(explicit.get("operation", "create"))
            target_ids = tuple(str(value) for value in explicit.get("target_ids", ()))
        demand_id = "demand:" + canonical_digest({
            "task_id": outcome.task_id,
            "family": outcome.family,
            "failure": failure,
            "operation": operation,
        })[:24]
        evidence_ids = tuple(event.evidence_id for event in matching)
        return StructuralDemand(
            demand_id,
            outcome.task_id,
            outcome.family,
            failure,
            operation,
            evidence_ids,
            target_ids,
            canonical_digest({
                "demand_id": demand_id,
                "evidence_ids": evidence_ids,
                "operation": operation,
            }),
        )

    def _semantic_node_ids(self, family: str) -> tuple[str, ...]:
        prefix = f"semantic:{family}:"
        return tuple(
            node.node_id for node in self._graph.snapshot().nodes
            if node.active and node.node_id.startswith(prefix)
        )

    def _build_create(self, demand: StructuralDemand) -> tuple[SemanticEdit, ...]:
        node_id = f"semantic:{demand.family}:{canonical_digest(demand.signal)[:12]}"
        if self._graph.snapshot().node(node_id) is not None:
            return ()
        payload = {
            "kind": "semantic",
            "label": f"{demand.family}:{demand.signal}",
            "content": f"Semantic slot for {demand.family} evidence and {demand.signal}.",
            "evidence_ids": demand.evidence_ids,
            "parent_ids": ("memory:outcome",),
        }
        edits = (
            SemanticEdit(
                "edit:create:" + node_id,
                "create",
                node_id,
                payload,
                "A repeated outcome cannot be represented by the current typed architecture.",
                canonical_digest({"operation": "create", "node_id": node_id, "payload": payload}),
            ),
            SemanticEdit(
                "edit:link:" + node_id,
                "create_edge",
                "edge:" + node_id,
                {"source_id": "memory:outcome", "target_id": node_id, "relation": "explains"},
                "Connect the new semantic slot to verified outcomes.",
                canonical_digest({"operation": "create_edge", "node_id": node_id}),
            ),
        )
        return edits

    def _build_split(self, demand: StructuralDemand) -> tuple[SemanticEdit, ...]:
        source_id = demand.target_ids[0] if demand.target_ids else (
            self._semantic_node_ids(demand.family)[0]
            if self._semantic_node_ids(demand.family) else ""
        )
        if not source_id:
            return self._build_create(demand)
        base = self._graph.snapshot().node(source_id)
        if base is None:
            return self._build_create(demand)
        left_id = f"{source_id}:a"
        right_id = f"{source_id}:b"
        edits = []
        for edge in self._graph.snapshot().edges:
            if edge.active and (edge.source_id == source_id or edge.target_id == source_id):
                edge_id = f"edge:{edge.source_id}:{edge.target_id}:{edge.relation}"
                edits.append(SemanticEdit(
                    f"edit:retire:{edge_id}", "retire_edge", edge_id, {
                        "source_id": edge.source_id, "target_id": edge.target_id,
                        "relation": edge.relation,
                    },
                    "Retire an edge attached to the split source.",
                    canonical_digest({"operation": "retire_edge", "target": edge_id}),
                ))
        edits.append(SemanticEdit(
            f"edit:retire:{source_id}", "retire_node", source_id, {},
            "Retire the over-broad semantic node before splitting it.",
            canonical_digest({"operation": "retire_node", "target": source_id}),
        ))
        for new_id, suffix in ((left_id, "verified"), (right_id, "unresolved")):
            edits.append(SemanticEdit(
                f"edit:create:{new_id}", "create", new_id,
                {
                    "kind": base.kind,
                    "label": f"{base.label}:{suffix}",
                    "content": f"{base.content} Split branch: {suffix}.",
                    "evidence_ids": demand.evidence_ids,
                    "parent_ids": base.parent_ids,
                },
                "Separate two meanings that were conflated by one semantic node.",
                canonical_digest({"operation": "create", "target": new_id}),
            ))
        return tuple(edits[:8])

    def _build_merge(self, demand: StructuralDemand) -> tuple[SemanticEdit, ...]:
        source_ids = demand.target_ids or self._semantic_node_ids(demand.family)
        source_ids = tuple(source_ids[:2])
        if len(source_ids) < 2:
            return self._build_create(demand)
        nodes = [self._graph.snapshot().node(node_id) for node_id in source_ids]
        if any(node is None for node in nodes):
            return self._build_create(demand)
        target_id = f"semantic:{demand.family}:merged"
        content = "Merged semantic representation: " + " / ".join(node.content for node in nodes if node)
        edits = [
            SemanticEdit(
                "edit:create:" + target_id, "create", target_id,
                {
                    "kind": "semantic",
                    "label": f"{demand.family}:merged",
                    "content": content,
                    "evidence_ids": demand.evidence_ids,
                    "parent_ids": ("memory:outcome",),
                },
                "Merge duplicate semantic nodes with compatible evidence.",
                canonical_digest({"operation": "merge", "target": target_id}),
            ),
            SemanticEdit(
                "edit:link:" + target_id, "create_edge", "edge:" + target_id,
                {"source_id": "memory:outcome", "target_id": target_id, "relation": "explains"},
                "Connect the merged semantic node to outcomes.",
                canonical_digest({"operation": "create_edge", "target": target_id}),
            ),
        ]
        for source_id in source_ids:
            for edge in self._graph.snapshot().edges:
                if edge.active and (edge.source_id == source_id or edge.target_id == source_id):
                    edge_id = f"edge:{edge.source_id}:{edge.target_id}:{edge.relation}"
                    edits.append(SemanticEdit(
                        f"edit:retire:{edge_id}", "retire_edge", edge_id, {
                            "source_id": edge.source_id, "target_id": edge.target_id,
                            "relation": edge.relation,
                        },
                        "Retire an edge attached to a merged source.",
                        canonical_digest({"operation": "retire_edge", "target": edge_id}),
                    ))
            edits.append(SemanticEdit(
                f"edit:retire:{source_id}", "retire_node", source_id, {},
                "Retire a redundant source after merge.",
                canonical_digest({"operation": "retire_node", "target": source_id}),
            ))
        return tuple(edits[:8])

    def _build_retire(self, demand: StructuralDemand) -> tuple[SemanticEdit, ...]:
        edits: list[SemanticEdit] = []
        target_ids = demand.target_ids or self._semantic_node_ids(demand.family)
        for target_id in target_ids[:4]:
            if self._graph.snapshot().node(target_id) is None:
                continue
            for edge in self._graph.snapshot().edges:
                if edge.active and (edge.source_id == target_id or edge.target_id == target_id):
                    edge_id = f"edge:{edge.source_id}:{edge.target_id}:{edge.relation}"
                    edits.append(SemanticEdit(
                        f"edit:retire:{edge_id}", "retire_edge", edge_id, {
                            "source_id": edge.source_id, "target_id": edge.target_id,
                            "relation": edge.relation,
                        },
                        "Retire an edge attached to an obsolete semantic node.",
                        canonical_digest({"operation": "retire_edge", "target": edge_id}),
                    ))
            edits.append(SemanticEdit(
                f"edit:retire:{target_id}", "retire_node", target_id, {},
                "Retire an obsolete semantic node after new evidence.",
                canonical_digest({"operation": "retire_node", "target": target_id}),
            ))
        return tuple(edits[:8])

    def _propose(self, demand: StructuralDemand) -> EvolutionCandidate:
        builders = {
            "create": self._build_create,
            "split": self._build_split,
            "merge": self._build_merge,
            "retire": self._build_retire,
        }
        edits = builders.get(demand.operation, self._build_create)(demand)
        return EvolutionCandidate(
            "candidate:" + demand.digest[:24],
            demand,
            edits,
            "PROPOSED" if edits else "NO_EDIT",
            "Semantic demand translated into a bounded topology edit.",
            self._graph.snapshot().digest(),
            demand.evidence_ids,
            canonical_digest({
                "demand": demand.digest,
                "edits": tuple(edit.digest for edit in edits),
                "base": self._graph.snapshot().digest(),
            }),
        )

    def _materialize_edit(self, edit: SemanticEdit) -> MemoryGraphOperation:
        if edit.operation == "create":
            return MemoryGraphOperation("create_node", edit.target_id, edit.payload)
        if edit.operation == "create_edge":
            return MemoryGraphOperation("create_edge", edit.target_id, edit.payload)
        if edit.operation == "retire_node":
            return MemoryGraphOperation("retire_node", edit.target_id, {})
        if edit.operation == "retire_edge":
            return MemoryGraphOperation("retire_edge", edit.target_id, edit.payload)
        if edit.operation == "update_node":
            return MemoryGraphOperation("update_node", edit.target_id, edit.payload)
        raise ValueError(f"unsupported SEM edit operation: {edit.operation}")

    def _apply_candidate(self, candidate: EvolutionCandidate) -> bool:
        if not candidate.edits:
            self._rejected_count += 1
            return False
        try:
            transaction = self._graph.stage(
                tuple(self._materialize_edit(edit) for edit in candidate.edits),
                evidence_ids=candidate.backfill_ids,
                rationale_digest=candidate.digest,
            )
            self._graph.activate(transaction)
        except (MemoryGraphConflict, ValueError) as exc:
            self._rejected_count += 1
            self._evolution_events.append({
                "event": "candidate_rejected",
                "candidate_id": candidate.candidate_id,
                "reason": str(exc),
            })
            return False
        self._adopted_count += 1
        self._backfilled_count += len(candidate.backfill_ids)
        self._evolution_events.append({
            "event": "candidate_adopted",
            "candidate_id": candidate.candidate_id,
            "operation": candidate.demand.operation,
            "family": candidate.demand.family,
            "backfill_count": len(candidate.backfill_ids),
            "generation": self.generation,
        })
        return True

    def task_completed(
        self,
        result: object,
        context: object,
        *,
        evolution_feedback: Mapping[str, Any] | None = None,
    ) -> MethodTaskCompletionReceipt:
        self._ensure_open()
        outcome = self._coerce_outcome(result)
        key = canonical_digest({"session": self.session_id, "task_id": outcome.task_id})
        if key in self._completed:
            return MethodTaskCompletionReceipt(key, self.generation)
        self._completed.add(key)
        payload = dict(outcome)
        payload["context"] = str(context)
        event = self._record_evidence(
            payload, source="task_completion",
            task_id=outcome.task_id, family=outcome.family,
        )
        self._route_evidence(event)
        if self.adaptive and not outcome.success:
            self._mismatch_count += 1
            demand = self._detect_demand(outcome)
            self._demands.append(demand)
            candidate = self._propose(demand)
            self._candidates.append(candidate)
            self._candidate_count += 1
            self._apply_candidate(candidate)
        return MethodTaskCompletionReceipt(
            key, self.generation,
            tuple(event.evidence_id for event in self._evidence[-1:]),
        )

    def reconcile_task_completion(self, completion_key: str, context: object) -> MethodTaskCompletionReceipt | None:
        if completion_key not in self._completed:
            return None
        return MethodTaskCompletionReceipt(completion_key, self.generation)

    @staticmethod
    def _snapshot_dict(snapshot: MemoryGraphSnapshot) -> dict[str, Any]:
        return {
            "schema_version": snapshot.schema_version,
            "generation": snapshot.generation,
            "nodes": [
                {
                    "node_id": node.node_id, "kind": node.kind, "label": node.label,
                    "content": node.content, "generation": node.generation,
                    "active": node.active, "evidence_ids": list(node.evidence_ids),
                    "parent_ids": list(node.parent_ids),
                }
                for node in snapshot.nodes
            ],
            "edges": [
                {
                    "source_id": edge.source_id, "target_id": edge.target_id,
                    "relation": edge.relation, "active": edge.active,
                }
                for edge in snapshot.edges
            ],
        }

    @staticmethod
    def _snapshot_from_dict(document: Mapping[str, Any]) -> MemoryGraphSnapshot:
        return MemoryGraphSnapshot(
            str(document["generation"]),
            tuple(
                MemoryNodeRecord(
                    str(row["node_id"]), str(row["kind"]), str(row["label"]),
                    str(row["content"]), str(row["generation"]),
                    bool(row["active"]), tuple(row["evidence_ids"]),
                    tuple(row["parent_ids"]),
                )
                for row in document["nodes"]
            ),
            tuple(
                MemoryEdgeRecord(
                    str(row["source_id"]), str(row["target_id"]),
                    str(row["relation"]), bool(row["active"]),
                )
                for row in document["edges"]
            ),
            str(document["schema_version"]),
        )

    def checkpoint(self) -> MethodSnapshot:
        self._ensure_open()
        payload = {
            "session_id": self.session_id,
            "treatment_id": self.treatment_id,
            "seed": self.seed,
            "generation": self.generation,
            "queries": self._queries,
            "completed": sorted(self._completed),
            "entries": [entry.__dict__ if hasattr(entry, "__dict__") else {
                "entry_id": entry.entry_id, "text": entry.text,
                "source": entry.source, "generation": entry.generation,
                "digest": entry.digest,
            } for entry in self._entries],
            "evidence": [
                {
                    "evidence_id": event.evidence_id, "task_id": event.task_id,
                    "family": event.family, "payload": dict(event.payload),
                    "source": event.source, "generation": event.generation,
                    "digest": event.digest,
                }
                for event in self._evidence
            ],
            "graph": self._snapshot_dict(self._graph.snapshot()),
            "demands": [demand.__dict__ if hasattr(demand, "__dict__") else {
                "demand_id": demand.demand_id, "task_id": demand.task_id,
                "family": demand.family, "signal": demand.signal,
                "operation": demand.operation, "evidence_ids": list(demand.evidence_ids),
                "target_ids": list(demand.target_ids), "digest": demand.digest,
            } for demand in self._demands],
            "evolution_events": list(self._evolution_events),
            "candidate_count": self._candidate_count,
            "adopted_count": self._adopted_count,
            "rejected_count": self._rejected_count,
            "backfilled_count": self._backfilled_count,
            "mismatch_count": self._mismatch_count,
        }
        opaque = canonical_bytes(payload)
        return MethodSnapshot(
            SEM_METHOD_ID, "3.0.0", "1",
            canonical_digest({"session_id": self.session_id, "treatment": self.treatment_id}),
            self.session_id, hashlib.sha256(opaque).hexdigest(), opaque,
        )

    def restore(self, snapshot: MethodSnapshot) -> None:
        self._ensure_open()
        if snapshot.session_id != self.session_id or snapshot.method_id != SEM_METHOD_ID:
            raise ValueError("SEM snapshot identity mismatch")
        if hashlib.sha256(snapshot.opaque_payload).hexdigest() != snapshot.payload_sha256:
            raise ValueError("SEM snapshot checksum mismatch")
        data = json.loads(snapshot.opaque_payload.decode("utf-8"))
        if data["treatment_id"] != self.treatment_id or data["seed"] != self.seed:
            raise ValueError("SEM snapshot treatment/seed mismatch")
        self._queries = int(data["queries"])
        self._completed = set(data["completed"])
        self._entries = [MemoryEntry(**row) for row in data["entries"]]
        self._evidence = [
            EvidenceEvent(
                str(row["evidence_id"]), str(row["task_id"]), str(row["family"]),
                dict(row["payload"]), str(row["source"]), str(row["generation"]),
                str(row["digest"]),
            )
            for row in data["evidence"]
        ]
        self._graph.restore(self._snapshot_from_dict(data["graph"]))
        self._demands = [
            StructuralDemand(
                str(row["demand_id"]), str(row["task_id"]), str(row["family"]),
                str(row["signal"]), str(row["operation"]),
                tuple(row["evidence_ids"]), tuple(row["target_ids"]), str(row["digest"]),
            )
            for row in data.get("demands", [])
        ]
        self._evolution_events = list(data.get("evolution_events", []))
        self._candidate_count = int(data.get("candidate_count", 0))
        self._adopted_count = int(data.get("adopted_count", 0))
        self._rejected_count = int(data.get("rejected_count", 0))
        self._backfilled_count = int(data.get("backfilled_count", 0))
        self._mismatch_count = int(data.get("mismatch_count", 0))

    def diagnostics(self) -> Mapping[str, Any]:
        graph = self._graph.diagnostics()
        return {
            "session_id": self.session_id,
            "treatment_id": self.treatment_id,
            "generation": self.generation,
            "graph_digest": graph["graph_digest"],
            "node_count": graph["node_count"],
            "active_node_count": graph["active_node_count"],
            "edge_count": graph["edge_count"],
            "memory_entry_count": len(self._entries),
            "evidence_count": len(self._evidence),
            "memory_queries": self._queries,
            "completed_task_count": len(self._completed),
            "structural_mismatch_count": self._mismatch_count,
            "candidate_count": self._candidate_count,
            "adopted_count": self._adopted_count,
            "rejected_count": self._rejected_count,
            "historical_backfill_count": self._backfilled_count,
            "evolution_event_count": len(self._evolution_events),
            "adaptive": self.adaptive,
            "closed": self._closed,
        }

    def close(self) -> None:
        self._closed = True

    def run(self, *, task: object, input_value: object, context: object) -> object:
        self._ensure_open()
        self.ingest({"task": str(task), "input": str(input_value)}, context)
        return self.recall(RecallRequest(str(task), context))


__all__ = [
    "SEM_METHOD_ID",
    "SEM_TREATMENTS",
    "EvidenceEvent",
    "EvolutionCandidate",
    "EvolutionEdit",
    "MemoryEntry",
    "SEMMethodSession",
    "SemanticEdit",
    "StructuralDemand",
]