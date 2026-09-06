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
        return EvolutionCandidate(
            f"candidate-{matched}",
            (edit,),
            "PROPOSED",
            edit.rationale,
            canonical_digest({"status": "PROPOSED", "edits": (edit.digest,)}),
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

    def ingest(self, evidence: Any, context: object) -> None:
        self._ensure_open()
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

    def task_completion_key(self, context: object) -> str:
        return canonical_digest({"session": self.session_id, "context": str(context)})

    def task_completed(self, result: object, context: object) -> MethodTaskCompletionReceipt:
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
        if self.adaptive and not outcome.success:
            candidate = self._evolver.propose(outcome.failure_reason, outcome.task_id)
            if candidate.edits:
                self._generation += 1
                for edit in candidate.edits:
                    self._append(edit.replacement, f"candidate:{candidate.candidate_id}", self.generation)
        return MethodTaskCompletionReceipt(key, self.generation)

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
        self._entries = [MemoryEntry(**row) for row in data["entries"]]

    def diagnostics(self) -> Mapping[str, Any]:
        return {
            "session_id": self.session_id,
            "treatment_id": self.treatment_id,
            "generation": self.generation,
            "entry_count": len(self._entries),
            "memory_queries": self._queries,
            "completed_task_count": len(self._completed),
            "adaptive": self.adaptive,
            "closed": self._closed,
        }

    def close(self) -> None:
        self._closed = True

    def run(self, *, task: object, input_value: object, context: object) -> object:
        self._ensure_open()
        self.ingest({"task": str(task), "input": str(input_value)}, context)
        return self.recall(RecallRequest(str(task), context))
