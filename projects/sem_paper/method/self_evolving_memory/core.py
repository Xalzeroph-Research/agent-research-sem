from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from noetrium.contracts import (
    AgentMemoryContext,
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


@dataclass(frozen=True, slots=True)
class MemoryEntry:
    entry_id: str
    text: str
    source: str
    generation: str
    digest: str


@dataclass(frozen=True, slots=True)
class EvolutionEdit:
    edit_id: str
    rationale: str
    replacement: str
    digest: str


@dataclass(frozen=True, slots=True)
class EvolutionCandidate:
    candidate_id: str
    edits: tuple[EvolutionEdit, ...]
    status: str
    reason: str
    digest: str


class RuleBasedEvolver:
    """Small deterministic proposer used by the SEM treatment.

    A candidate is explicit and auditable. An empty candidate is a valid
    NO_EDIT decision with a reason, never an unconditional silent no-op.
    """

    def propose(self, failure_reason: str, recent_text: str) -> EvolutionCandidate:
        failure = (failure_reason or "").strip().lower()
        signals = {
            "timeout": "Use shorter action batches and re-observe before continuing.",
            "blocked": "Verify prerequisites and retry from the last grounded state.",
            "missing": "Record the missing prerequisite before planning the next action.",
            "precondition_missing": "Query the grounded state before selecting a dependency-producing action.",
            "path_interrupted": "Re-observe the route and use a bounded movement segment.",
            "no_threats": "Do not treat an empty threat set as combat success.",
            "partial_effect": "Reconcile effect receipt before issuing a retry.",
            "provider_error": "Record provider failure and stop unsafe retries.",
        }
        matched = next((key for key in signals if key in failure), None)
        if matched is None and failure:
            rationale = "Preserve the current policy; failure is not covered by a safe rule."
            return EvolutionCandidate(
                "candidate-no-edit",
                (),
                "NO_EDIT",
                rationale,
                canonical_digest({"status": "NO_EDIT", "reason": rationale}),
            )
        if matched is None:
            return EvolutionCandidate(
                "candidate-no-edit",
                (),
                "NO_EDIT",
                "No failure signal was supplied.",
                canonical_digest({"status": "NO_EDIT", "reason": "no failure"}),
            )
        replacement = signals[matched]
        edit = EvolutionEdit(
            f"edit-{matched}",
            f"Failure signal {matched!r} matched a bounded SEM rule.",
            replacement,
            canonical_digest({"signal": matched, "replacement": replacement}),
        )
        candidate_id = (
            f"candidate-{matched}-"
            f"{canonical_digest({'failure': matched, 'recent': recent_text})[:10]}"
        )
        return EvolutionCandidate(
            candidate_id,
            (edit,),
            "PROPOSED",
            edit.rationale,
            canonical_digest({
                "candidate_id": candidate_id,
                "status": "PROPOSED",
                "edits": (edit.digest,),
            }),
        )


class SEMMethodSession:
    """Concrete SEM MethodSession consumed by environment/cognition adapters."""

    task_completion_idempotency = "sem.method-task-completion.v2"

    def __init__(
        self,
        *,
        session_id: str,
        treatment_id: str,
        seed: str,
        adaptive: bool,
        initial_memory: tuple[str, ...] = (),
    ) -> None:
        if not session_id.strip() or not treatment_id.strip() or not seed.strip():
            raise ValueError("SEM session identity is required")
        if treatment_id not in {"fixed_memory", "rule_based", "self_evolving"}:
            raise ValueError("unknown SEM treatment")
        self.session_id = session_id
        self.treatment_id = treatment_id
        self.seed = seed
        self.adaptive = adaptive
        self._generation = 0
        self._closed = False
        self._queries = 0
        self._completed: set[str] = set()
        self._entries: list[MemoryEntry] = []
        self._evolver = RuleBasedEvolver()
        self._policy_overrides: dict[str, str] = {}
        self._pending_candidates: dict[str, EvolutionCandidate] = {}
        self._evolution_events: list[dict[str, Any]] = []
        self._candidate_count = 0
        self._adopted_count = 0
        self._rejected_count = 0
        for index, text in enumerate(initial_memory):
            self._append(text, "initial", f"g{self._generation}", index)

    @property
    def generation(self) -> str:
        return f"g{self._generation}"

    @property
    def program_identity(self) -> MethodProgramIdentity:
        return MethodProgramIdentity(
            MethodIdentity("self_evolving_memory", "2.0.0", "1", "1"),
            canonical_digest({"treatment": self.treatment_id, "seed": self.seed}),
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("SEM session is closed")

    def _append(self, text: str, source: str, generation: str, index: int | None = None) -> MemoryEntry:
        normalized = " ".join(str(text).split())
        if not normalized:
            raise ValueError("SEM memory entry cannot be empty")
        entry_id = f"entry-{len(self._entries) if index is None else index}-{len(self._entries)}"
        entry = MemoryEntry(
            entry_id,
            normalized,
            source,
            generation,
            canonical_digest({"text": normalized, "source": source, "generation": generation}),
        )
        self._entries.append(entry)
        return entry

    def ingest(
        self,
        evidence: Any,
        context: object,
        *,
        persistent: bool = True,
    ) -> None:
        self._ensure_open()
        if not persistent and self.treatment_id == "fixed_memory":
            return
        if self.treatment_id == "fixed_memory" and persistent:
            self._evolution_events.append({
                "event": "memory_update_rejected",
                "reason": "fixed_memory_is_immutable",
            })
            return
        if isinstance(evidence, Mapping):
            text = json.dumps(evidence, sort_keys=True, ensure_ascii=False)
        else:
            text = str(evidence)
        self._append(text, "environment", self.generation)

    def recall(self, request: RecallRequest) -> RecallResult:
        self._ensure_open()
        self._queries += 1
        intent = set(str(request.intent).lower().split())
        ranked = sorted(
            self._entries,
            key=lambda entry: (
                len(intent.intersection(entry.text.lower().split())),
                entry.entry_id,
            ),
            reverse=True,
        )[: max(1, request.limit)]
        context_text = "\n".join(entry.text for entry in ranked)
        return RecallResult(context_text, self.generation, tuple(entry.digest for entry in ranked))

    def plan_actions(self, task: Mapping[str, Any]) -> tuple[tuple[str, Mapping[str, Any], float], ...]:
        """Return the method-owned action plan consumed by an environment adapter.

        The environment executes and verifies these intents; it does not invent a
        second hidden policy. The plan is deliberately deterministic and auditable.
        """
        family = str(task.get("family", ""))
        plans = {
            "resource_collection": (("collect_block", {"block": "oak_log", "count": 4, "max_distance": 64}, 240.0),),
            "crafting_tech_tree": (
                ("craft_item", {"item": "oak_planks", "count": 16}, 60.0),
                ("collect_block", {"block": "cobblestone", "count": 3, "max_distance": 32}, 180.0),
                ("craft_item", {"item": "stone_pickaxe", "count": 1}, 90.0),
            ),
            "navigation_return": (
                ("move_away", {"distance": 16}, 120.0),
                ("goto", {"position": {"x": 9.5, "y": 72, "z": 168.5}, "radius": 5}, 180.0),
            ),
            "combat_survival": (("defend_self", {"radius": 32, "max_targets": 1, "max_hits": 8}, 180.0),),
            "simple_building": (
                ("craft_item", {"item": "crafting_table", "count": 1}, 90.0),
                ("craft_item", {"item": "chest", "count": 1}, 90.0),
                ("place_block", {"item": "crafting_table"}, 90.0),
                ("place_block", {"item": "chest"}, 90.0),
            ),
            "long_horizon_mixed": (
                ("collect_block", {"block": "iron_ore", "count": 1, "max_distance": 64}, 240.0),
                ("craft_item", {"item": "shield", "count": 1}, 120.0),
            ),
        }
        plan = tuple(plans.get(family, ()))
        policy_hint = self._policy_overrides.get(family)
        if policy_hint:
            plan = tuple(
                (action_type, {**dict(arguments), "_sem_policy_hint": policy_hint}, budget)
                for action_type, arguments, budget in plan
            )
        return plan

    def task_completion_key(self, context: object) -> str:
        return canonical_digest({"session": self.session_id, "context": str(context)})

    def task_completed(
        self,
        result: object,
        context: object,
        *,
        evolution_feedback: Mapping[str, Any] | None = None,
    ) -> MethodTaskCompletionReceipt:
        self._ensure_open()
        if isinstance(result, MethodTaskOutcome):
            outcome = result
        elif isinstance(result, Mapping):
            outcome = MethodTaskOutcome(
                task_id=str(result["task_id"]),
                family=str(result.get("family", "unknown")),
                lineage_id=str(result.get("lineage_id", result["task_id"])),
                success=bool(result["success"]),
                utility=float(result.get("utility", 0.0)),
                steps=int(result.get("steps", 0)),
                failure_reason=str(result.get("failure_reason", "")),
                memory_queries=int(result.get("memory_queries", self._queries)),
            )
        else:
            raise TypeError("SEM task completion requires MethodTaskOutcome or mapping")
        key = canonical_digest({"session": self.session_id, "task_id": outcome.task_id})
        if key in self._completed:
            return MethodTaskCompletionReceipt(key, self.generation)
        self._completed.add(key)
        self.ingest(dict(outcome), context)
        if self.adaptive and not outcome.success and not self._pending_candidates:
            candidate = self._evolver.propose(outcome.failure_reason, outcome.task_id)
            if candidate.edits:
                self._candidate_count += 1
                self._pending_candidates[candidate.candidate_id] = candidate
                self._evolution_events.append({
                    "event": "candidate_proposed",
                    "candidate_id": candidate.candidate_id,
                    "task_id": outcome.task_id,
                    "family": outcome.family,
                    "treatment": self.treatment_id,
                })
                if self.treatment_id == "rule_based":
                    self._adopt_candidate(candidate, outcome.family, "rule_policy")
                elif evolution_feedback is not None:
                    self.validate_and_apply(
                        candidate.candidate_id,
                        outcome.family,
                        evolution_feedback,
                    )
        return MethodTaskCompletionReceipt(key, self.generation)

    def _adopt_candidate(self, candidate: EvolutionCandidate, family: str, reason: str) -> None:
        self._generation += 1
        self._adopted_count += 1
        self._policy_overrides[family] = candidate.candidate_id
        for edit in candidate.edits:
            self._append(edit.replacement, f"candidate:{candidate.candidate_id}", self.generation)
        self._evolution_events.append({
            "event": "candidate_adopted",
            "candidate_id": candidate.candidate_id,
            "family": family,
            "reason": reason,
            "generation": self.generation,
        })
        self._pending_candidates.pop(candidate.candidate_id, None)

    def validate_and_apply(
        self,
        candidate_id: str,
        family: str,
        feedback: Mapping[str, Any],
    ) -> bool:
        self._ensure_open()
        candidate = self._pending_candidates.get(candidate_id)
        if candidate is None:
            raise KeyError(f"unknown SEM evolution candidate: {candidate_id}")
        verified = bool(feedback.get("verified", False))
        utility_delta = float(feedback.get("utility_delta", 0.0))
        if verified and utility_delta > 0.0:
            self._adopt_candidate(candidate, family, "shadow_validation")
            return True
        self._rejected_count += 1
        self._pending_candidates.pop(candidate_id, None)
        self._evolution_events.append({
            "event": "candidate_rejected",
            "candidate_id": candidate_id,
            "family": family,
            "verified": verified,
            "utility_delta": utility_delta,
        })
        return False

    def pending_candidates(self) -> tuple[EvolutionCandidate, ...]:
        return tuple(self._pending_candidates.values())

    def checkpoint(self) -> MethodSnapshot:
        self._ensure_open()
        payload = {
            "session_id": self.session_id,
            "treatment_id": self.treatment_id,
            "seed": self.seed,
            "adaptive": self.adaptive,
            "generation": self._generation,
            "queries": self._queries,
            "completed": sorted(self._completed),
            "policy_overrides": dict(sorted(self._policy_overrides.items())),
            "pending_candidates": {
                key: {
                    "candidate_id": value.candidate_id,
                    "status": value.status,
                    "reason": value.reason,
                    "digest": value.digest,
                    "edits": [
                        {"edit_id": edit.edit_id, "rationale": edit.rationale,
                         "replacement": edit.replacement, "digest": edit.digest}
                        for edit in value.edits
                    ],
                }
                for key, value in sorted(self._pending_candidates.items())
            },
            "evolution_events": list(self._evolution_events),
            "candidate_count": self._candidate_count,
            "adopted_count": self._adopted_count,
            "rejected_count": self._rejected_count,
            "entries": [entry.__dict__ if hasattr(entry, "__dict__") else {
                "entry_id": entry.entry_id, "text": entry.text,
                "source": entry.source, "generation": entry.generation, "digest": entry.digest
            } for entry in self._entries],
        }
        opaque = canonical_bytes(payload)
        return MethodSnapshot(
            "self_evolving_memory", "2.0.0", "1",
            canonical_digest({"session_id": self.session_id, "treatment": self.treatment_id}),
            self.session_id, hashlib.sha256(opaque).hexdigest(), opaque,
        )

    def restore(self, snapshot: MethodSnapshot) -> None:
        self._ensure_open()
        if snapshot.session_id != self.session_id or snapshot.method_id != "self_evolving_memory":
            raise ValueError("SEM snapshot identity mismatch")
        if hashlib.sha256(snapshot.opaque_payload).hexdigest() != snapshot.payload_sha256:
            raise ValueError("SEM snapshot checksum mismatch")
        data = json.loads(snapshot.opaque_payload.decode("utf-8"))
        if data["treatment_id"] != self.treatment_id or data["seed"] != self.seed:
            raise ValueError("SEM snapshot treatment/seed mismatch")
        self._generation = int(data["generation"])
        self._queries = int(data["queries"])
        self._completed = set(data["completed"])
        self._policy_overrides = dict(data.get("policy_overrides", {}))
        self._pending_candidates = {
            key: EvolutionCandidate(
                candidate_id=value["candidate_id"],
                edits=tuple(EvolutionEdit(**edit) for edit in value.get("edits", [])),
                status=value["status"], reason=value["reason"], digest=value["digest"],
            )
            for key, value in data.get("pending_candidates", {}).items()
        }
        self._evolution_events = list(data.get("evolution_events", []))
        self._candidate_count = int(data.get("candidate_count", 0))
        self._adopted_count = int(data.get("adopted_count", 0))
        self._rejected_count = int(data.get("rejected_count", 0))
        self._entries = [MemoryEntry(**row) for row in data["entries"]]

    def diagnostics(self) -> Mapping[str, Any]:
        return {
            "session_id": self.session_id,
            "treatment_id": self.treatment_id,
            "generation": self.generation,
            "entry_count": len(self._entries),
            "memory_queries": self._queries,
            "completed_task_count": len(self._completed),
            "pending_candidate_count": len(self._pending_candidates),
            "candidate_count": self._candidate_count,
            "adopted_count": self._adopted_count,
            "rejected_count": self._rejected_count,
            "evolution_events": len(self._evolution_events),
            "policy_overrides": dict(self._policy_overrides),
            "adaptive": self.adaptive,
            "closed": self._closed,
        }

    def close(self) -> None:
        self._closed = True

    def run(self, *, task: object, input_value: object, context: object) -> object:
        self._ensure_open()
        self.ingest({"task": str(task), "input": str(input_value)}, context)
        return self.recall(RecallRequest(str(task), context))
