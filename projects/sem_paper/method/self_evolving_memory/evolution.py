from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, TYPE_CHECKING

from noetrium.contracts import canonical_digest

if TYPE_CHECKING:
    from .core import EvolutionCandidate, StructuralDemand, SEMMethodSession


PROPOSAL_KINDS = frozenset({
    "NO_EDIT",
    "CREATE_NODE",
    "RETIRE_NODE",
    "SPLIT_NODE",
    "MERGE_NODES",
})


@dataclass(frozen=True, slots=True)
class SemanticProposal:
    proposal_id: str
    kind: str
    symptom_refs: tuple[str, ...]
    hypothesis: str
    edit: Mapping[str, Any]
    expected_effects: Mapping[str, Any]
    rationale: str
    source_refs: tuple[str, ...]
    digest: str

    def __post_init__(self) -> None:
        if self.kind not in PROPOSAL_KINDS:
            raise ValueError(f"unsupported semantic proposal kind: {self.kind}")
        if not self.proposal_id.strip() or not self.hypothesis.strip():
            raise ValueError("semantic proposal identity and hypothesis are required")
        if not isinstance(self.edit, Mapping):
            raise TypeError("semantic proposal edit must be a mapping")
        if "confidence" in self.edit or "approved" in self.edit:
            raise ValueError("semantic proposal cannot self-approve")
        required = (
            self.symptom_refs, self.source_refs,
            self.expected_effects, self.rationale,
        )
        if any(value is None for value in required):
            raise ValueError("semantic proposal fields cannot be null")

    @classmethod
    def build(
        cls,
        *,
        proposal_id: str,
        kind: str,
        symptom_refs: Iterable[str],
        hypothesis: str,
        edit: Mapping[str, Any],
        expected_effects: Mapping[str, Any],
        rationale: str,
        source_refs: Iterable[str],
    ) -> "SemanticProposal":
        symptoms = tuple(str(item) for item in symptom_refs)
        sources = tuple(str(item) for item in source_refs)
        payload = {
            "proposal_id": proposal_id,
            "kind": kind,
            "symptom_refs": symptoms,
            "hypothesis": hypothesis,
            "edit": dict(edit),
            "expected_effects": dict(expected_effects),
            "rationale": rationale,
            "source_refs": sources,
        }
        return cls(
            proposal_id, kind, symptoms, hypothesis, dict(edit),
            dict(expected_effects), rationale, sources,
            canonical_digest(payload),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "kind": self.kind,
            "symptom_refs": list(self.symptom_refs),
            "hypothesis": self.hypothesis,
            "edit": dict(self.edit),
            "expected_effects": dict(self.expected_effects),
            "rationale": self.rationale,
            "source_refs": list(self.source_refs),
            "digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class EvolutionLedgerEntry:
    sequence: int
    event: str
    generation: str
    proposal_id: str
    candidate_id: str
    payload: Mapping[str, Any]
    digest: str


class EvolutionLedger:
    """Append-only downstream ledger for proposals, validation, and adoption."""

    def __init__(self) -> None:
        self._entries: list[EvolutionLedgerEntry] = []

    def append(
        self,
        event: str,
        *,
        generation: str,
        proposal_id: str = "",
        candidate_id: str = "",
        payload: Mapping[str, Any] = (),
    ) -> EvolutionLedgerEntry:
        sequence = len(self._entries)
        body = {
            "sequence": sequence,
            "event": event,
            "generation": generation,
            "proposal_id": proposal_id,
            "candidate_id": candidate_id,
            "payload": dict(payload),
        }
        entry = EvolutionLedgerEntry(
            sequence, event, generation, proposal_id, candidate_id,
            dict(payload), canonical_digest(body),
        )
        self._entries.append(entry)
        return entry

    @property
    def entries(self) -> tuple[EvolutionLedgerEntry, ...]:
        return tuple(self._entries)

    def digest(self) -> str:
        return canonical_digest([
            {
                "sequence": item.sequence,
                "event": item.event,
                "generation": item.generation,
                "proposal_id": item.proposal_id,
                "candidate_id": item.candidate_id,
                "payload": dict(item.payload),
                "digest": item.digest,
            }
            for item in self._entries
        ])

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                "sequence": item.sequence,
                "event": item.event,
                "generation": item.generation,
                "proposal_id": item.proposal_id,
                "candidate_id": item.candidate_id,
                "payload": dict(item.payload),
                "digest": item.digest,
            }
            for item in self._entries
        ]

    def restore(self, rows: Iterable[Mapping[str, Any]]) -> None:
        self._entries.clear()
        for row in rows:
            self._entries.append(EvolutionLedgerEntry(
                int(row["sequence"]),
                str(row["event"]),
                str(row["generation"]),
                str(row.get("proposal_id", "")),
                str(row.get("candidate_id", "")),
                dict(row.get("payload", {})),
                str(row["digest"]),
            ))


class EvolutionAuthority(Protocol):
    authority_id: str

    def propose(
        self,
        session: "SEMMethodSession",
        demand: "StructuralDemand",
    ) -> "EvolutionCandidate": ...


class MetaArchitectPort(EvolutionAuthority, Protocol):
    """Injection seam for a SEM Meta-Architect provider."""


class RuleBasedEvolver:
    """Deterministic control baseline sharing the graph and validation runtime."""

    authority_id = "rule_based_evolver.v1"

    def propose(
        self,
        session: "SEMMethodSession",
        demand: "StructuralDemand",
    ) -> "EvolutionCandidate":
        return session._propose_rule_based(demand)


__all__ = [
    "EvolutionAuthority",
    "EvolutionLedger",
    "EvolutionLedgerEntry",
    "MetaArchitectPort",
    "PROPOSAL_KINDS",
    "RuleBasedEvolver",
    "SemanticProposal",
]
